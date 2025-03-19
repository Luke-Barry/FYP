import asyncio
import logging
import os
import ssl
from typing import Dict, Optional

from aioquic.asyncio import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent
from aioquic.tls import SessionTicket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("server")

async def handle_stream(reader, writer):
    """Handle a QUIC stream"""
    try:
        # Read data from the stream
        data = await reader.read(1024)
        if data:
            message = data.decode()
            logger.info(f"Received: {message}")
            
            # Echo the message back
            writer.write(data)
            await writer.drain()
            logger.info(f"Echoed back: {message}")
    except Exception as e:
        logger.error(f"Stream error: {e}")
    finally:
        writer.close()

async def main():
    # Configure SSL key logging
    os.environ["SSLKEYLOGFILE"] = "ssl-keys.log"
    logger.info(f"SSL key logging enabled to {os.environ.get('SSLKEYLOGFILE')}")
    
    # Create QUIC configuration
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
    )
    
    # Load SSL certificate
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")
    
    # Define a proper stream handler wrapper that ensures the coroutine is awaited
    def create_stream_handler(reader, writer):
        asyncio.create_task(handle_stream(reader, writer))
    
    # Start server
    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        stream_handler=create_stream_handler
    )
    
    logger.info("QUIC server started on 0.0.0.0:8080")
    
    # Run forever
    await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
