import asyncio
import logging
import os
from typing import Optional, Tuple, Callable
from aioquic.asyncio import serve, QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicFrameType, Limit

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

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
    """Handles a single QUIC stream."""
    stream_id = writer.get_extra_info("stream_id")
    logger.info(f"Stream {stream_id} opened")
    try:
        while True:
            data = await reader.read(1024)
            if not data:
                break
            message = data.decode()
            logger.info(f"Received on stream {stream_id}: {message}")
    except Exception as e:
        logger.error(f"Error on stream {stream_id}: {e}")
    finally:
        logger.info(f"Stream {stream_id} closing")
        writer.close()

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
