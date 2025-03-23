import asyncio
import ssl
import os
import json
import time
import logging
from asyncio import Queue
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicFileLogger

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("client")

# Maximum QUIC packet size (1200 bytes is default, we'll use max allowed)
MAX_DATAGRAM_SIZE = 65527  # Maximum allowed by QUIC
MESSAGE_COUNT = 100  # Number of messages to send per stream

# --- Patch QuicConnection.get_next_available_stream_id for client-initiated bidirectional streams ---
_original_get_next_available_stream_id = QuicConnection.get_next_available_stream_id

def patched_get_next_available_stream_id(self, is_unidirectional: bool = False) -> int:
    if not is_unidirectional:
        if not hasattr(self, "_next_stream_id"):
            self._next_stream_id = 0
        stream_id = self._next_stream_id
        self._next_stream_id += 4
        return stream_id
    else:
        return _original_get_next_available_stream_id(self, is_unidirectional=is_unidirectional)

QuicConnection.get_next_available_stream_id = patched_get_next_available_stream_id
# --- End patch ---

class MyQuicConnectionProtocol(QuicConnectionProtocol):
    def __init__(self, quic, stream_handler: Optional[Callable] = None) -> None:
        super().__init__(quic, stream_handler)
        self._stream_creation_lock = asyncio.Lock()

    async def create_stream(self, is_unidirectional: bool = False) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        async with self._stream_creation_lock:
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=is_unidirectional)
            return self._create_stream(stream_id)

class ThroughputTester:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
        self.test_duration = 5  # Test duration in seconds
        self.message_sizes = [1024, 4096, 16384, 65527]  # 1KB, 4KB, 16KB, Max QUIC
        self.gc_enabled = True  # Enable garbage collection control
        
    async def run_size_test(self, size: int, streams: list):
        """Run throughput test with a specific message size across all streams concurrently"""
        # Force garbage collection before test
        if self.gc_enabled:
            import gc
            gc.collect()
            
        start_time = time.time()
        tasks = [self.send_messages(stream, size) for stream in streams]
        stream_results = await asyncio.gather(*tasks)
        
        # Calculate totals
        total_messages = sum(r['messages_sent'] for r in stream_results)
        total_bytes = sum(r['bytes_sent'] for r in stream_results)
        duration = time.time() - start_time
        
        # Calculate per-stream metrics
        per_stream_results = []
        for result in stream_results:
            stream_duration = duration  # Use same duration for consistency
            messages = result['messages_sent']
            bytes_sent = result['bytes_sent']
            per_stream_results.append({
                'stream_id': result['stream_id'],
                'messages_sent': messages,
                'bytes_sent': bytes_sent,
                'messages_per_second': messages / stream_duration,
                'bytes_per_second': bytes_sent / stream_duration,
                'mbits_per_second': (bytes_sent * 8 / 1_000_000) / stream_duration
            })
        
        return {
            'size': size,
            'duration': duration,
            'total_messages': total_messages,
            'total_bytes': total_bytes,
            'total_throughput_mbps': (total_bytes * 8 / 1_000_000) / duration,
            'messages_per_second': total_messages / duration,
            'per_stream_results': per_stream_results
        }
    
    async def send_messages(self, stream_info: dict, message_size: int):
        """Send messages on a single stream for the test duration"""
        writer = stream_info['writer']
        stream_id = stream_info['stream_id']
        
        # Create base message once and reuse
        base_message = b'X' * (message_size - 20)  # Leave room for message number
        messages_sent = 0
        bytes_sent = 0
        end_time = time.time() + self.test_duration
        
        while time.time() < end_time:
            try:
                # Reuse message object to reduce memory allocations
                message = f"{messages_sent:010d}".encode() + base_message[:message_size-10]
                async with stream_info['lock']:
                    writer.write(message)
                    await writer.drain()  # Wait for buffer to be sent
                    messages_sent += 1
                    bytes_sent += len(message)
                
                # Adaptive sleep based on system load
                if messages_sent % 50 == 0:  # Increased from 100 to reduce memory pressure
                    await asyncio.sleep(0.002)  # Increased sleep time slightly
                
                # Force garbage collection periodically
                if self.gc_enabled and messages_sent % 1000 == 0:
                    import gc
                    gc.collect()
                    
            except Exception as e:
                logger.error(f"Error sending message on stream {stream_id}: {e}")
                break
        
        return {
            'stream_id': stream_id,
            'messages_sent': messages_sent,
            'bytes_sent': bytes_sent
        }
    
    def save_aggregate_results(self, all_results: list):
        """Save the aggregate results to a JSON file"""
        first_result = all_results[0] if all_results else {}
        per_stream_results = first_result.get('per_stream_results', [])
        num_streams = len(per_stream_results)
        
        aggregate_results = {
            'test_duration': self.test_duration,
            'number_of_streams': num_streams,
            'message_size_results': all_results,
            'total_test_duration': time.time() - self.start_time
        }
        
        with open("/app/qlogs/aggregate_throughput_results.json", "w") as f:
            json.dump(aggregate_results, f, indent=2)
            logger.info("Aggregate results saved to /app/qlogs/aggregate_throughput_results.json")

# Global throughput tester
throughput_tester = ThroughputTester()

async def run_client(host: str, port: int, num_streams: int) -> None:
    qlog_dir = "/app/qlogs"
    os.makedirs(qlog_dir, exist_ok=True)  # Ensure qlog directory exists
    quic_logger = QuicFileLogger(qlog_dir)  # Pass directory, NOT file path

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE,
        quic_logger=quic_logger
    )
    configuration.max_streams_bidi = 100

    async with connect(host, port, configuration=configuration, create_protocol=MyQuicConnectionProtocol) as protocol:
        protocol._sender_lock = asyncio.Lock()
        logger.info("Connection established with server.")

        # Create streams in batches to reduce memory pressure
        streams = []
        batch_size = 10
        for i in range(1, num_streams + 1):
            try:
                reader, writer = await protocol.create_stream(is_unidirectional=False)
                stream_id = writer.get_extra_info("stream_id")
                streams.append({
                    'stream_id': stream_id,
                    'writer': writer,
                    'reader': reader,
                    'lock': asyncio.Lock(),
                    'queue_name': f'queue{i}'
                })
                logger.info(f"Created stream {stream_id} for queue{i}")
                
                # Add small delay between batches of stream creation
                if i % batch_size == 0:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error creating stream {i}: {e}")
                continue

        # Run tests for each message size across all streams concurrently
        all_results = []
        for size in throughput_tester.message_sizes:
            logger.info(f"\nStarting concurrent test with message size {size} bytes across all streams")
            result = await throughput_tester.run_size_test(size, streams)
            all_results.append(result)
            logger.info(f"Completed test for {size} bytes:")
            logger.info(f"Total throughput: {result['total_throughput_mbps']:.2f} Mbps")
            logger.info(f"Total messages/sec: {result['messages_per_second']:.2f}")
            # Add delay between tests
            await asyncio.sleep(1)

        # Save final results
        throughput_tester.save_aggregate_results(all_results)
        logger.info("All throughput tests completed successfully")

        # Clean up streams
        for stream in streams:
            stream['writer'].close()

if __name__ == "__main__":
    host = "quic-server"
    port = 8080

    # Get number of streams from environment variable, default to 3 if not set
    num_streams = int(os.getenv('NUM_STREAMS', 3))
    print(f"Starting client with {num_streams} streams")
    
    asyncio.run(run_client(host, port, num_streams))
