import asyncio
import logging
import os
from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

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