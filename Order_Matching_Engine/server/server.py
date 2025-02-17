import asyncio
import logging
import os
import json
from typing import Optional, Tuple, Callable
from enum import Enum
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicFrameType, Limit

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'
user_dict = {}

class Stream(Enum):
    ORDERS = 0
    MARKET_DATA = 4
    NOTIFICATIONS = 8

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

# (On the server side, incoming stream IDs come from the client.)
# If needed, you can similarly define a protocol subclass that protects stream creation.
class MyQuicConnectionProtocol(QuicConnectionProtocol):
    def __init__(self, quic: QuicConnection, stream_handler: Optional[Callable] = None) -> None:
        super().__init__(quic, stream_handler)
        self._stream_creation_lock = asyncio.Lock()

    async def create_stream(self, is_unidirectional: bool = False) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        async with self._stream_creation_lock:
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=is_unidirectional)
            return self._create_stream(stream_id)

async def handle_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    stream_id = writer.get_extra_info("stream_id")
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                continue
            message = data.decode()
            try:
                parsed_message = json.loads(message)
                if stream_id == Stream.ORDERS.value:
                    user = parsed_message['user']
                    order = parsed_message['data']
                    if order is None:
                        user_dict[user] = []
                        logger.info(f"Server established connection with user: {user}")
                    else:
                        user_dict[user].append(order)
                        logger.info(f"Server received order from {user}: {order}")
                else:
                    user = parsed_message['user']
                    data = parsed_message['data']
                    if user != 'MATCHING_ENGINE':
                        logger.info(f"{user} established connection on stream {stream_id}")
                    elif stream_id == Stream.MARKET_DATA.value:
                        publish_market_data(data)
                    elif stream_id == Stream.NOTIFICATIONS.value:
                        send_notifications(data)
            except json.JSONDecodeError:
                logger.error(f"Error decoding message on stream {stream_id}: {message}")
                continue
    except Exception as e:
        logger.error(f"Error on stream {stream_id}: {e}")
    finally:
        logger.info(f"Stream {stream_id} closing")
        writer.close()

def publish_market_data(market_data):
    return

def send_notifications(notification):
    return

async def main():
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
        # Optionally, you can use our subclass to protect any server-side stream creation:
        create_protocol=MyQuicConnectionProtocol,
        stream_handler=lambda r, w: asyncio.create_task(handle_stream(r, w))
    )

    logger.info("Server started on 0.0.0.0:8080")
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
