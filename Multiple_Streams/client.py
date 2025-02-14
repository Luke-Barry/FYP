import asyncio
import ssl
from asyncio import Queue
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection

# --- Patch QuicConnection.get_next_available_stream_id for client-initiated bidirectional streams ---
_original_get_next_available_stream_id = QuicConnection.get_next_available_stream_id

def patched_get_next_available_stream_id(self, is_unidirectional: bool = False) -> int:
    # For bidirectional streams (is_unidirectional=False), use a simple counter.
    if not is_unidirectional:
        if not hasattr(self, "_next_stream_id"):
            self._next_stream_id = 0
        stream_id = self._next_stream_id
        self._next_stream_id += 4
        return stream_id
    else:
        # For unidirectional streams, use the original behavior.
        return _original_get_next_available_stream_id(self, is_unidirectional=is_unidirectional)

QuicConnection.get_next_available_stream_id = patched_get_next_available_stream_id
# --- End patch ---

# Subclass QuicConnectionProtocol to protect stream creation with a lock.
class MyQuicConnectionProtocol(QuicConnectionProtocol):
    def __init__(self, quic, stream_handler: Optional[Callable] = None) -> None:
        super().__init__(quic, stream_handler)
        self._stream_creation_lock = asyncio.Lock()

    async def create_stream(self, is_unidirectional: bool = False) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        async with self._stream_creation_lock:
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=is_unidirectional)
            return self._create_stream(stream_id)

async def send_from_queue(protocol: MyQuicConnectionProtocol, queue: Queue, queue_name: str) -> None:
    """Create a new bidirectional stream and send messages from the given queue."""
    reader, writer = await protocol.create_stream(is_unidirectional=False)
    stream_id = writer.get_extra_info("stream_id")
    print(f"Created stream {stream_id} for {queue_name}")
    
    while True:
        message = await queue.get()
        if message is None:
            break
        async with protocol._sender_lock:
            writer.write(message.encode())
            await writer.drain()
            print(f"Sent on stream {stream_id}: {message}")
            await asyncio.sleep(0.01)
    print(f"Queue {queue_name} on stream {stream_id} finished")
    # Do not call writer.write_eof() so that the stream remains open if needed.

async def run_client(host: str, port: int) -> None:
    # Create a message queue for each logical channel.
    queues = {
        'queue1': Queue(),
        'queue2': Queue(),
        'queue3': Queue()
    }
    # Populate the queues with messages.
    for i in range(5):
        for queue_name, queue in queues.items():
            await queue.put(f"Message {i+1} from {queue_name}")
    # Add a sentinel (None) to mark the end of each queue.
    for queue in queues.values():
        await queue.put(None)

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )
    configuration.max_streams_bidi = 100

    # Use our protocol subclass by specifying create_protocol.
    async with connect(host, port, configuration=configuration, create_protocol=MyQuicConnectionProtocol) as protocol:
        protocol._sender_lock = asyncio.Lock()
        print("Connection established with server.")

        tasks = []
        for queue_name, queue in queues.items():
            tasks.append(asyncio.create_task(send_from_queue(protocol, queue, queue_name)))
        await asyncio.gather(*tasks)
        print("All streams completed successfully")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))
