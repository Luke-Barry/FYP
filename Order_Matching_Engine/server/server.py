import asyncio
import logging
import os
import json
from typing import Optional, Tuple, Callable
from enum import Enum
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicFrameType, Limit

# Setup enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("server")
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'
user_dict = {}

class Stream(Enum):
    ORDERS = 0
    MARKET_DATA = 4
    NOTIFICATIONS = 8

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
            try:
                parsed_message = json.loads(data.decode())
                if 'user' not in parsed_message or 'data' not in parsed_message:
                    logger.error(f"Received message missing required fields: {parsed_message}")
                    continue

                user = parsed_message['user']
                data = parsed_message['data']

                if data is None:
                    user_dict[(user, stream_id)] = (reader, writer)
                    logger.info(f"Server established connection with user: {user} on stream: {stream_id}")
                elif stream_id == Stream.ORDERS.value:
                    logger.info(f"Server received order from {user}: {data}, forwarding to matching engine.")
                    await forward_order(data)
                elif stream_id == Stream.MARKET_DATA.value:
                    logger.info(f"Server received market data from {user}, forwarding to client.")
                    await forward_market_data(user, data)
                elif stream_id == Stream.NOTIFICATIONS.value:
                    logger.info(f"Server received notification from {user}, forwarding to client.")
                    await forward_notifications(user, data)
            except json.JSONDecodeError:
                logger.error(f"Error decoding message on stream {stream_id}: {parsed_message}")
                continue
    except Exception as e:
        logger.error(f"Error on stream {stream_id}: {e}")
    finally:
        logger.info(f"Stream {stream_id} closing")
        writer.close()

async def forward_market_data(user: str, nested_data):
    for (target_user, target_stream_id), (_, writer) in user_dict.items():
        if target_stream_id == Stream.MARKET_DATA.value:
            writer.write(json.dumps({"user": user, "data": nested_data}).encode())
            await writer.drain()

async def forward_notifications(user: str, nested_data):
    target_user = nested_data["target_user"]
    message = nested_data["message"]
    if (target_user, Stream.NOTIFICATIONS.value) in user_dict:
        _, writer = user_dict[(target_user, Stream.NOTIFICATIONS.value)]
        try:
            # Ensure we're sending a clean, properly formatted message
            writer.write(json.dumps({
                "user": user,
                "data": message
            }).encode() + b"\n")  # Add newline to separate messages
            await writer.drain()
            logger.info(f"Server forwarded notification to {target_user}: {message}")
        except Exception as e:
            logger.error(f"Error forwarding notification: {e}")
    else:
        logger.warning(f"Cannot forward notification to {target_user}: User not connected")

async def forward_order(order):
    while ("MATCHING_ENGINE", 0) not in user_dict:
        logger.error("Error, Matching engine has yet to connect to server, please wait.")
        await asyncio.sleep(1)
    matching_engine_writer = user_dict[("MATCHING_ENGINE", 0)][1]
    matching_engine_writer.write(json.dumps({"user": "SERVER", "data": order}).encode())
    await matching_engine_writer.drain()

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