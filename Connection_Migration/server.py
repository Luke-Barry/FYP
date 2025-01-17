import asyncio
import logging
import os
from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

# Set the SSL keylog file environment variable
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

async def handle_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handles bidirectional streams."""
    try:
        while True:
            # Read data from the stream
            data = await reader.read(1024)  # Adjust buffer size if needed
            if not data:  # Connection is closed
                break
            message = data.decode()
            logger.info(f"Received: {message}")

            # Echo the message back to the client
            writer.write(data)
            await writer.drain()  # Ensure the data is sent
    except Exception as e:
        logger.error(f"Stream error: {e}")
    finally:
        logger.info("Closing stream")
        writer.close()
        await writer.wait_closed()

def stream_handler_wrapper(reader, writer):
    """Wrapper to properly invoke the handle_stream coroutine."""
    asyncio.ensure_future(handle_stream(reader, writer))

async def main():
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )

    # Load SSL certificate and private key
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")

    # Start the QUIC server with a stream handler
    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        stream_handler=stream_handler_wrapper,  # Use the wrapper
    )

    logger.info("Server started on 0.0.0.0:8080")
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
