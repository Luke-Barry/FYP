import asyncio
import logging
import os
import time
import json
import signal
from typing import Optional, Tuple, Callable, Dict
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicFrameType, Limit

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

class MetricsManager:
    def __init__(self):
        self.metrics = {}
        self.start_time = time.time()
        self.last_save_time = time.time()
        os.makedirs("/app/qlogs", exist_ok=True)
        
    def init_stream(self, stream_id: int):
        self.metrics[stream_id] = {
            "messages_received": 0,
            "bytes_received": 0,
            "start_time": time.time(),
            "last_message_time": None
        }
        
    def record_message(self, stream_id: int, size: int):
        if stream_id in self.metrics:
            self.metrics[stream_id]["messages_received"] += 1
            self.metrics[stream_id]["bytes_received"] += size
            self.metrics[stream_id]["last_message_time"] = time.time()
            
            # Save metrics every 5 seconds
            current_time = time.time()
            if current_time - self.last_save_time >= 5:
                self.save_performance_metrics()
                self.last_save_time = current_time
            
    def get_stream_metrics(self, stream_id: int):
        if stream_id not in self.metrics:
            return None
            
        m = self.metrics[stream_id]
        duration = m["last_message_time"] - m["start_time"] if m["last_message_time"] else 0
        
        return {
            "messages_received": m["messages_received"],
            "bytes_received": m["bytes_received"],
            "duration_seconds": duration,
            "messages_per_second": m["messages_received"] / duration if duration > 0 else 0,
            "bytes_per_second": m["bytes_received"] / duration if duration > 0 else 0,
            "mbits_per_second": (m["bytes_received"] * 8 / 1_000_000) / duration if duration > 0 else 0
        }
        
    def get_aggregate_metrics(self):
        if not self.metrics:
            return {
                "total_duration_seconds": 0,
                "total_messages": 0,
                "total_bytes": 0,
                "total_messages_per_second": 0,
                "total_bytes_per_second": 0,
                "total_mbits_per_second": 0,
                "number_of_streams": 0,
                "streams": {}
            }
            
        total_duration = time.time() - self.start_time
        total_messages = sum(m["messages_received"] for m in self.metrics.values())
        total_bytes = sum(m["bytes_received"] for m in self.metrics.values())
        
        return {
            "total_duration_seconds": total_duration,
            "total_messages": total_messages,
            "total_bytes": total_bytes,
            "total_messages_per_second": total_messages / total_duration if total_duration > 0 else 0,
            "total_bytes_per_second": total_bytes / total_duration if total_duration > 0 else 0,
            "total_mbits_per_second": (total_bytes * 8 / 1_000_000) / total_duration if total_duration > 0 else 0,
            "number_of_streams": len(self.metrics),
            "streams": {
                str(stream_id): self.get_stream_metrics(stream_id)
                for stream_id in self.metrics
            }
        }
        
    def save_performance_metrics(self):
        metrics = self.get_aggregate_metrics()
        # Reformatting metrics to match the old structure with packet size breakdown
        formatted_metrics = {
            "test_duration": metrics["total_duration_seconds"],
            "number_of_streams": metrics["number_of_streams"],
            "message_size_results": [],
            "total_test_duration": metrics["total_duration_seconds"]
        }

        # Group metrics by message size
        for size, data in metrics["streams"].items():
            message_size_result = {
                "size": size,
                "duration": data["duration_seconds"],
                "total_messages": data["messages_received"],
                "total_bytes": data["bytes_received"],
                "total_throughput_mbps": data["mbits_per_second"],
                "messages_per_second": data["messages_per_second"],
                "per_stream_results": data
            }
            formatted_metrics["message_size_results"].append(message_size_result)

        with open("/app/qlogs/aggregate_throughput_results.json", "w") as f:
            json.dump(formatted_metrics, f, indent=2)
            logger.info("Performance metrics saved to /app/qlogs/aggregate_throughput_results.json")

# --- Patch QuicConnection to use a custom max_streams_bidi limit if provided ---
_original_init = QuicConnection.__init__

def patched_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    if hasattr(self._configuration, "max_streams_bidi"):
        self._local_max_streams_bidi = Limit(
            frame_type=QuicFrameType.MAX_STREAMS_BIDI,
            name="max_streams_bidi",
            value=self._configuration.max_streams_bidi,
        )

QuicConnection.__init__ = patched_init
# --- End patch ---

# Global metrics manager
metrics_manager = MetricsManager()

class MyQuicConnectionProtocol(QuicConnectionProtocol):
    def __init__(self, quic: QuicConnection, stream_handler: Optional[Callable] = None) -> None:
        super().__init__(quic, stream_handler)
        self._stream_creation_lock = asyncio.Lock()

    async def create_stream(self, is_unidirectional: bool = False) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        async with self._stream_creation_lock:
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=is_unidirectional)
            return self._create_stream(stream_id)

async def handle_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handles a single QUIC stream."""
    stream_id = writer.get_extra_info("stream_id")
    metrics_manager.init_stream(stream_id)
    
    logger.info(f"Stream {stream_id} opened")
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
                
            # Track metrics without modifying the data flow
            metrics_manager.record_message(stream_id, len(data))
            
            # Echo the data back (original functionality)
            writer.write(data)
            await writer.drain()
            
    except Exception as e:
        logger.error(f"Error on stream {stream_id}: {e}")
    finally:
        logger.info(f"Stream {stream_id} closing")
        writer.close()

async def shutdown(signal, loop):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    signals = (signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(shutdown(s, loop))
        )

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )
    configuration.max_streams_bidi = 100
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")

    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        create_protocol=MyQuicConnectionProtocol,
        stream_handler=lambda r, w: asyncio.create_task(handle_stream(r, w))
    )

    logger.info("Server started on 0.0.0.0:8080")
    
    try:
        await asyncio.Future()  # run forever
    finally:
        server.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
