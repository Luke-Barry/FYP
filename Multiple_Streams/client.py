import asyncio
import ssl
import os
import json
import time
from asyncio import Queue
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicFileLogger

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

async def send_from_queue(protocol: MyQuicConnectionProtocol, queue: Queue, queue_name: str) -> None:
    reader, writer = await protocol.create_stream(is_unidirectional=False)
    stream_id = writer.get_extra_info("stream_id")
    print(f"Created stream {stream_id} for {queue_name}")

    # Create messages of different sizes to test throughput
    message_sizes = [1024, 4096, 16384, 65527]  # 1KB, 4KB, 16KB, Max QUIC
    results = []
    
    for size in message_sizes:
        base_message = b'X' * (size - 20)  # Leave room for message number
        start_time = time.time()
        bytes_sent = 0
        messages_sent = 0
        
        # Send messages for 5 seconds for each size
        end_time = start_time + 5
        
        while time.time() < end_time:
            message = f"{messages_sent}:".encode() + base_message
            async with protocol._sender_lock:
                writer.write(message)
                await writer.drain()
                bytes_sent += len(message)
                messages_sent += 1
        
        duration = time.time() - start_time
        throughput_mbps = (bytes_sent * 8 / 1_000_000) / duration
        messages_per_sec = messages_sent / duration
        
        results.append({
            'size': size,
            'duration': duration,
            'messages_sent': messages_sent,
            'bytes_sent': bytes_sent,
            'throughput_mbps': throughput_mbps,
            'messages_per_sec': messages_per_sec
        })
        
        print(f"\nStream {stream_id} results for {size} byte messages:")
        print(f"Throughput: {throughput_mbps:.2f} Mbps")
        print(f"Messages/sec: {messages_per_sec:.2f}")
        print(f"Total messages: {messages_sent}")
        
        # Small pause between different message sizes
        await asyncio.sleep(1)
    
    # Save results to a file
    results_file = f"/app/qlogs/throughput_results_{stream_id}.json"
    with open(results_file, "w") as f:
        json.dump({
            'stream_id': stream_id,
            'queue_name': queue_name,
            'results': results
        }, f, indent=2)
    
    print(f"Queue {queue_name} on stream {stream_id} finished")
    writer.close()

async def run_client(host: str, port: int) -> None:
    os.makedirs("/app/qlogs", exist_ok=True)

    queues = {
        'queue1': Queue(),
        'queue2': Queue(),
        'queue3': Queue()
    }

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
        print("Connection established with server.")

        tasks = [asyncio.create_task(send_from_queue(protocol, queue, queue_name)) 
                for queue_name, queue in queues.items()]
        await asyncio.gather(*tasks)
        print("All streams completed successfully")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))
