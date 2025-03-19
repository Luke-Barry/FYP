import asyncio
import ssl
import os
import logging
import signal
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.logger import QuicFileLogger

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("client")

# Global shutdown event
shutdown_event = None

def handle_signal(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}")

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

async def run_client(host: str, port: int) -> None:
    # Use relative path for qlogs
    qlog_dir = "./qlogs"
    os.makedirs(qlog_dir, exist_ok=True)
    
    # Generate unique connection ID for the log file
    connection_id = os.urandom(8).hex()
    quic_logger = QuicFileLogger(qlog_dir)

    # Ensure the keylog file directory exists
    keylog_dir = "./certs"
    os.makedirs(keylog_dir, exist_ok=True)
    keylog_path = os.path.join(keylog_dir, "ssl_keylog.txt")

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open(keylog_path, "a"),
        verify_mode=ssl.CERT_NONE,
        quic_logger=quic_logger
    )

    try:
        async with connect(host, port, configuration=configuration) as protocol:
            logger.info("Connection established with server.")
            logger.info(f"Logging to {qlog_dir} with connection ID {connection_id}")

            # Create a bidirectional stream
            reader, writer = await protocol.create_stream(is_unidirectional=False)

            for i in range(10):
                message = f"Hello from QUIC client! Message {i + 1}"
                writer.write(message.encode())
                await writer.drain()
                logger.info(f"Sent: {message}")

                # Wait before sending the next message
                await asyncio.sleep(2.5)

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
    finally:
        # Ensure proper cleanup
        if 'writer' in locals() and not writer.is_closing():
            writer.close()
            await writer.wait_closed()
        logger.info("Client shutdown complete")

def main():
    host = "quic-server"
    port = 8080
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_client(host, port))
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        loop.close()

if __name__ == "__main__":
    main()