import asyncio
import ssl
import os
import json
import logging
import threading
from flask import Flask, request, jsonify
from typing import Tuple, Optional, Callable, Dict, List
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("client")

username = os.getenv("USER_ID", "DEFAULT")
app = Flask(__name__)

# --- Global state ---
event_loop = None
order_queue = None
order_stream = None
is_initialized = False
current_orderbook = {"bids": [], "asks": []}
user_orders: Dict[str, List[Dict]] = {}
notifications = []  # List to store notifications
state_lock = threading.Lock()

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
        """Create a new bidirectional stream."""
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
        logger.info(f"Started handling stream: {stream_name}")
        
        while True:
            try:
                data = await reader.read(1024)
                if not data:
                    break
                    
                message = json.loads(data.decode())
                logger.info(f"Received on {stream_name}: {message}")
                
                # Update state based on message type
                with state_lock:
                    if "data" in message and isinstance(message["data"], dict):
                        if "data" in message["data"]:
                            # Handle market data updates
                            market_data = message["data"]["data"]
                            if isinstance(market_data, dict) and ("bids" in market_data or "asks" in market_data):
                                current_orderbook["bids"] = market_data.get("bids", [])
                                current_orderbook["asks"] = market_data.get("asks", [])
                                logger.info(f"Updated orderbook: {current_orderbook}")
                        else:
                            # This is a notification - copy directly without modification
                            notification = message["data"]
                            logger.info(f"Received notification: {notification}")
                            notifications.append(notification)
                            
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
            await asyncio.sleep(0.1)
            
    except asyncio.CancelledError:
        logger.warning(f"{stream_name} stream task cancelled.")
    except Exception as e:
        logger.error(f"Error in {stream_name} stream: {e}")
    finally:
        logger.info(f"Stream {stream_name} handler ending")

@app.route('/api/orders/<user_id>')
def get_user_orders(user_id):
    """Returns the user's orders and latest notifications."""
    try:
        with state_lock:
            # Convert notifications to display format without removing them
            latest_notifications = []
            for notification in notifications:
                # Format the notification for display
                notification_type = notification.get('type', '').upper()
                
                # Create formatted notification
                formatted_notification = {
                    'type': notification_type,
                    'order_id': notification.get('order_id', ''),
                    'price': notification.get('price', 0),
                    'quantity': notification.get('quantity', 0),
                    'side': notification.get('side', '')
                }
                
                latest_notifications.append(formatted_notification)
                
            return jsonify({
                "notifications": latest_notifications
            }), 200
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/orderbook')
def get_orderbook():
    """Returns the current orderbook state."""
    try:
        with state_lock:
            return jsonify(current_orderbook), 200
    except Exception as e:
        logger.error(f"Error getting orderbook: {e}")
        return jsonify({"error": str(e)}), 500

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

        # Ensure all required fields are present
        required_fields = ["type", "side", "quantity"]
        if data.get("type") == "limit":
            required_fields.append("price")
            
        if not all(field in data for field in required_fields):
            logger.error(f"Missing required fields. Required: {required_fields}")
            return jsonify({"error": "Missing required fields"}), 400

        # Convert numeric strings to numbers
        if "price" in data:
            data["price"] = float(data["price"])
        data["quantity"] = int(data["quantity"])

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

@app.route('/api/order/<order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """Cancel a specific order."""
    try:
        if not order_stream:
            return jsonify({"error": "Order stream not initialized"}), 500

        # Send cancel request through QUIC stream
        message = {
            "type": "CANCEL_ORDER",
            "order_id": order_id,
            "user": username
        }
        
        # Send the cancel request through the order stream
        order_stream.write(json.dumps({"user": username, "data": message}).encode())
        event_loop.call_soon_threadsafe(order_stream.drain)
        
        return jsonify({"message": "Cancel request sent"}), 200
        
    except Exception as e:
        logger.error(f"Error sending cancel request: {e}")
        return jsonify({"error": str(e)}), 500

async def send_orders(order_queue: asyncio.Queue, writer: asyncio.StreamWriter):
    """Processes the order queue from web GUI and sends orders to server."""
    if not writer:
        logger.error("Orders stream not available.")
        return
    
    try:
        # Initial empty message to establish stream
        writer.write(json.dumps({"user": username, "data": None}).encode())
        await writer.drain()
        
        while True:
            order = await order_queue.get()
            # Add username to order
            order["user"] = username
            logger.info(f"Sending order from queue: {order}")
            writer.write(json.dumps({"user": username, "data": order}).encode())
            await writer.drain()
    except Exception as e:
        logger.error(f"Error in send_orders: {e}")
    finally:
        logger.info("Send orders task ending")

async def run_client(host: str, port: int) -> None:
    global event_loop, order_queue, is_initialized, order_stream

    event_loop = asyncio.get_event_loop()  # Store event loop for Flask
    order_queue = asyncio.Queue()
    is_initialized = True  # Mark initialization as complete

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        verify_mode=ssl.CERT_NONE  # Don't verify certificates
    )
    configuration.max_streams_bidi = 100

    try:
        async with connect(
            host=host,
            port=port,
            configuration=configuration,
            create_protocol=MyQuicConnectionProtocol
        ) as protocol:
            logger.info("Connection established with server.")

            # Create streams for different purposes
            order_reader, order_stream = await protocol.create_stream()
            notification_reader, notification_writer = await protocol.create_stream()
            market_reader, market_writer = await protocol.create_stream()

            # Start handlers for each stream
            order_handler = asyncio.create_task(send_orders(order_queue, order_stream))
            notification_handler = asyncio.create_task(handle_incoming_stream(notification_reader, notification_writer))
            market_handler = asyncio.create_task(handle_incoming_stream(market_reader, market_writer))

            try:
                await asyncio.gather(order_handler, notification_handler, market_handler)
            except Exception as e:
                logger.error(f"Client error: {e}")
            finally:
                # Cancel all tasks
                order_handler.cancel()
                notification_handler.cancel()
                market_handler.cancel()
                
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise

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
