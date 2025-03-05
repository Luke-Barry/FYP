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
        
    async def run_size_test(self, size: int, streams: list):
        """Run throughput test with a specific message size across all streams concurrently"""
        start_time = time.time()
        tasks = [self.send_messages(stream, size) for stream in streams]
        results = await asyncio.gather(*tasks)
        
        # Aggregate results for this message size
        total_messages = sum(r['messages_sent'] for r in results)
        total_bytes = sum(r['bytes_sent'] for r in results)
        duration = time.time() - start_time
        
        return {
            'size': size,
            'duration': duration,
            'total_messages': total_messages,
            'total_bytes': total_bytes,
            'total_throughput_mbps': (total_bytes * 8 / 1_000_000) / duration,
            'messages_per_second': total_messages / duration,
            'per_stream_results': results
        }
    
    async def send_messages(self, stream_info: dict, message_size: int):
        """Send messages on a single stream for the test duration"""
        writer = stream_info['writer']
        stream_id = stream_info['stream_id']
        base_message = b'X' * (message_size - 20)  # Leave room for message number
        
        messages_sent = 0
        bytes_sent = 0
        end_time = time.time() + self.test_duration
        
        while time.time() < end_time:
            message = f"{messages_sent}:".encode() + base_message
            async with stream_info['lock']:
                writer.write(message)
                await writer.drain()
                messages_sent += 1
                bytes_sent += len(message)
        
        return {
            'stream_id': stream_id,
            'messages_sent': messages_sent,
            'bytes_sent': bytes_sent
        }
    
    def save_aggregate_results(self, all_results: list):
        aggregate_results = {
            'test_duration': self.test_duration,
            'number_of_streams': len(self.results),
            'message_size_results': all_results,
            'total_test_duration': time.time() - self.start_time
        }
        
        with open("/app/qlogs/aggregate_throughput_results.json", "w") as f:
            json.dump(aggregate_results, f, indent=2)
            logger.info("Aggregate results saved to /app/qlogs/aggregate_throughput_results.json")

# Global throughput tester
throughput_tester = ThroughputTester()

async def run_client(host: str, port: int) -> None:
    os.makedirs("/app/qlogs", exist_ok=True)
    logger.info("Created directory /app/qlogs")

    # Create the specified number of queues
    queues = {f'queue{i}': Queue() for i in range(1, 4)}

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=MAX_DATAGRAM_SIZE,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )
    configuration.max_streams_bidi = 100

    async with connect(host, port, configuration=configuration, create_protocol=MyQuicConnectionProtocol) as protocol:
        protocol._sender_lock = asyncio.Lock()
        logger.info("Connection established with server.")

        # Create all streams first
        streams = []
        for queue_name in queues:
            reader, writer = await protocol.create_stream(is_unidirectional=False)
            stream_id = writer.get_extra_info("stream_id")
            streams.append({
                'stream_id': stream_id,
                'writer': writer,
                'reader': reader,
                'lock': asyncio.Lock(),
                'queue_name': queue_name
            })
            logger.info(f"Created stream {stream_id} for {queue_name}")

        # Run tests for each message size across all streams concurrently
        all_results = []
        for size in throughput_tester.message_sizes:
            logger.info(f"\nStarting concurrent test with message size {size} bytes across all streams")
            result = await throughput_tester.run_size_test(size, streams)
            all_results.append(result)
            logger.info(f"Completed test for {size} bytes:")
            logger.info(f"Total throughput: {result['total_throughput_mbps']:.2f} Mbps")
            logger.info(f"Total messages/sec: {result['messages_per_second']:.2f}")
            await asyncio.sleep(1)  # Short pause between size tests

        # Save final results
        throughput_tester.save_aggregate_results(all_results)
        logger.info("All throughput tests completed successfully")

        # Clean up streams
        for stream in streams:
            stream['writer'].close()

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))
