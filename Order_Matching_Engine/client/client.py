import asyncio
import ssl
import os
import json
import logging
import threading
from flask import Flask, request, jsonify
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("client")

username = os.getenv("USER_ID", "DEFAULT")
app = Flask(__name__)

# --- Global event loop for thread-safe operations ---
event_loop = None
order_queue = None
is_initialized = False  # Flag to track initialization

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
            logger.info(f"Established stream: {stream_id}")
            return reader, writer

async def handle_incoming_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Handles incoming messages on a given stream (either for notifications or market data)."""
    try:
        writer.write(json.dumps({"user": username, "data": None}).encode())  
        await writer.drain()
        stream_name = writer.get_extra_info("stream_id")
        while True:
            data = await reader.read(1024)
            if data:
                logger.info(f"Received on {stream_name}: {data.decode()}")
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.warning(f"{stream_name} stream task cancelled.")
    except Exception as e:
        logger.error(f"Error in {stream_name} stream: {e}")

@app.route('/api/order', methods=['POST'])
def receive_order():
    """Receives orders via HTTP POST and adds them to the order queue."""
    try:
        # Log if the client is initialized
        if not is_initialized:
            logger.error("Client is not initialized yet.")
            return jsonify({"error": "Client is not initialized yet."}), 503

        data = request.get_json()
        if not data:
            logger.error("Invalid JSON received.")
            return jsonify({"error": "Invalid JSON"}), 400

        logger.info(f"Received order from web server: {data}")
        
        # Use the stored event loop to enqueue orders properly
        if event_loop is None:
            logger.error("Event loop is not available.")
            return jsonify({"error": "Event loop is not available."}), 500

        logger.info("Enqueuing order to event loop.")
        asyncio.run_coroutine_threadsafe(order_queue.put(data), event_loop)

        return jsonify({"success": True, "order": data}), 200

    except Exception as e:
        logger.error(f"Error receiving order: {e}")
        return jsonify({"error": str(e)}), 500

async def send_orders(order_queue: asyncio.Queue, writer: asyncio.StreamWriter):
    """Processes the order queue from web GUI and sends orders to server."""
    if not writer:
        logger.error("Orders stream not available.")
        return
    
    # Initial empty message to establish stream
    writer.write(json.dumps({"user": username, "data": None}).encode())
    await writer.drain()
    
    while True:
        order = await order_queue.get()
        logger.info(f"Sending order from queue: {order}")
        writer.write(json.dumps({"user": username, "data": order}).encode())
        await writer.drain()

async def run_client(host: str, port: int) -> None:
    global event_loop, order_queue, is_initialized

    event_loop = asyncio.get_event_loop()  # Store event loop for Flask
    order_queue = asyncio.Queue()
    is_initialized = True  # Mark initialization as complete

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
        logger.info("Connection established with server.")

        _, orders_writer = await protocol.create_stream()
        market_reader, market_writer = await protocol.create_stream()
        notifications_reader, notifications_writer = await protocol.create_stream()

        # Start tasks for QUIC communication
        tasks = [
            asyncio.create_task(handle_incoming_stream(market_reader, market_writer)),
            asyncio.create_task(handle_incoming_stream(notifications_reader, notifications_writer)),
            asyncio.create_task(send_orders(order_queue, orders_writer))
        ]

        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            logger.info("Client shutting down gracefully.")

def start_flask():
    """Runs Flask API in a separate thread."""
    app.run(debug=False, host='0.0.0.0', port=6060, use_reloader=False)

if __name__ == "__main__":
    # Start Flask API in a separate thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))  # Start the client connection and event loop
