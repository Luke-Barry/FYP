import asyncio
import logging
import os
from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection, QuicFrameType, Limit

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

# --- Patch QuicConnection to use a custom max_streams_bidi limit ---
_original_init = QuicConnection.__init__

def patched_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    # If our configuration defines a custom limit, override the default limit.
    if hasattr(self._configuration, "max_streams_bidi"):
        self._local_max_streams_bidi = Limit(
            frame_type=QuicFrameType.MAX_STREAMS_BIDI,
            name="max_streams_bidi",
            value=self._configuration.max_streams_bidi,
        )

QuicConnection.__init__ = patched_init
# --- End patch ---

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
    # Create a configuration and set a custom maximum number of bidirectional streams.
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )
    # Set your desired bidirectional streams limit here.
    configuration.max_streams_bidi = 100  
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")

    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        stream_handler=lambda r, w: asyncio.create_task(handle_stream(r, w))
    )

    logger.info("Server started on 0.0.0.0:8080")
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
