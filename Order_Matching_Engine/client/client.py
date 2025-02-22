import asyncio
import ssl
import os
import json
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection

username = os.getenv("USER_ID", "DEFAULT")

# --- Patch QuicConnection.get_next_available_stream_id ---
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

    async def create_stream(self) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Create a new bidirectional stream and store its reader/writer pair."""
        async with self._stream_creation_lock:
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=False)
            reader, writer = self._create_stream(stream_id)
            print(f"Established stream: {stream_id}")
            return reader, writer

async def handle_incoming_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handles incoming messages on a given stream (either for notifications or market data)."""
    try:
        writer.write(json.dumps({"user": username, "data": None}).encode())  # ✅ Fix: Encode before writing
        stream_name = writer.get_extra_info("stream_id")
        while True:
            data = await reader.read(1024)  # Wait for data
            if data:  # Process only non-empty messages
                print(f"Received on {stream_name}: {data.decode()}")
            await asyncio.sleep(0.1)  # Prevent CPU-intensive busy-waiting
    except asyncio.CancelledError:
        print(f"{stream_name} stream task cancelled.")
    except Exception as e:
        print(f"Error in {stream_name} stream: {e}")

async def send_orders(order_queue: asyncio.Queue, writer: asyncio.StreamWriter):
    """Processes the order queue and sends orders to the server when available."""
    if not writer:
        print("Orders stream not available.")
        return
    writer.write((json.dumps({"user": username, "data": None})).encode())
    await writer.drain()
    await asyncio.sleep(3)
    writer.write((json.dumps({"user": username, "data": "order placeholer"})).encode())
    while True:
        # order = await order_queue.get()  # Wait for an order to be available
        # writer.write((order + "\n").encode())  # Send each order separately with a newline
        # await writer.drain()
        # print(f"Sent order: {order}")
        # order_queue.task_done()
        await asyncio.sleep(0.5)  # Adjust as needed to control send rate

async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )
    configuration.max_streams_bidi = 100

    async with connect(host, port, configuration=configuration, create_protocol=MyQuicConnectionProtocol) as protocol:
        protocol._sender_lock = asyncio.Lock()
        print("Connection established with server.")

        order_queue = asyncio.Queue()

        _, orders_writer = await protocol.create_stream()
        market_reader, market_writer = await protocol.create_stream()
        notifications_reader, notifications_writer = await protocol.create_stream()

        tasks = [
            asyncio.create_task(handle_incoming_stream(market_reader, market_writer)),
            asyncio.create_task(handle_incoming_stream(notifications_reader, notifications_writer)),
            asyncio.create_task(send_orders(order_queue, orders_writer)),  # Pass the queue explicitly
        ]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            print("Client shutting down gracefully.")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))
