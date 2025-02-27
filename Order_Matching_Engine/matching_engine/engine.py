import asyncio
import ssl
import os
import json
import logging
from typing import Tuple, Optional, Callable
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from orderbook import OrderBook

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine")

username = os.getenv("USER_ID", "DEFAULT")
writer_dict = {}
order_book = OrderBook()

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
            initial_message = {"user": username, "data": None}
            writer.write((json.dumps(initial_message)).encode())
            logger.info(f"Established stream: {stream_id}")
            return reader, writer

async def handle_incoming_orders(reader: asyncio.StreamReader):
    """Handles incoming messages on a given stream (either for notifications or market data)"""
    try:
        while True:
            data = await reader.read(1024)
            if data:
                order_data = json.loads(data.decode())
                data = order_data['data']
                response_user = data['user']
                type = data['type']
                if type == "limit":
                    order_id, matches = order_book.add_limit_order(
                        data['side'],
                        data['price'],
                        data['quantity'],
                        response_user
                    )
                    await send_market_data({"user": username, "data": order_book.get_market_data()})
                    await send_notifications(response_user, {"type": "order_posted", "order_id": order_id})
                    for price, quantity, matched_user in matches:
                        await send_notifications(matched_user, {"type": "order_matched", "price": price, "quantity": quantity})
                elif type == "cancel":
                    success = order_book.cancel_limit_order(
                        response_user,
                        data['price'],
                        data['quantity'],
                        data['side']
                    )
                    if success:
                        await send_market_data({"user": username, "data": order_book.get_market_data()})
                        await send_notifications(response_user, {"type": "order_cancelled"})
                    else:
                        await send_notifications(response_user, {"type": "cancel_failed"})
                elif type == "market":
                    matches = order_book.match_market_order(
                        data['side'],
                        data['quantity']
                    )
                    await send_market_data({"user": username, "data": order_book.get_market_data()})
                    for price, quantity, matched_user in matches:
                        await send_notifications(matched_user, {"type": "order_matched", "price": price, "quantity": quantity})

            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.warning("Order receival task cancelled.")
    except Exception as e:
        logger.error(f"Error in orders stream: {e}")

async def send_market_data(data: dict):
    if "market_data" in writer_dict:
        writer_dict["market_data"].write(json.dumps({"user": username, "data": data}).encode())
    logger.info("Matching engine sending market data back to server")

async def send_notifications(target_user: str, message: dict):
    if "notifications" in writer_dict:
        writer_dict["notifications"].write(json.dumps({
            "user": username,
            "data": {
                "target_user": target_user,
                "message": message
            }
        }).encode())
    logger.info("Matching engine sending notifications back to server")
    await asyncio.sleep(0.0001)

async def run_matching_engine(host: str, port: int) -> None:
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

        orders_reader, _ = await protocol.create_stream()
        _, market_writer = await protocol.create_stream()
        _, notifications_writer = await protocol.create_stream()

        writer_dict["market_data"] = market_writer
        writer_dict["notifications"] = notifications_writer

        tasks = [asyncio.create_task(handle_incoming_orders(orders_reader))]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            logger.info("Client shutting down gracefully.")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_matching_engine(host, port))