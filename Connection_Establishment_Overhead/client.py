import asyncio
import logging
import os
import ssl
import time

from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, HandshakeCompleted, StreamDataReceived
from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import SessionTicket

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("client")

# Create directories for logs and certs
os.makedirs("./qlogs", exist_ok=True)
os.makedirs("./certs", exist_ok=True)

async def run_client(host, port):
    """Create and run a QUIC client connection"""
    # Create QUIC configuration
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        verify_mode=ssl.CERT_NONE,
        quic_logger=QuicFileLogger("./qlogs")
    )
    
    # Load certificate
    configuration.load_verify_locations("certs/ssl_cert.pem")
    
    # Connect to the server
    async with connect(
        host,
        port,
        configuration=configuration,
        wait_connected=True
    ) as client:
        # Send message
        message = f"Hello from QUIC client at {time.time()}"
        
        # Send data on a new stream
        stream_id = client._quic.get_next_available_stream_id()
        client._quic.send_stream_data(stream_id, message.encode())
        logger.info(f"Sent message: {message}")
        
        # Wait for the response and events
        response_received = False
        
        # Try for 5 seconds
        start_time = time.time()
        while time.time() - start_time < 5:
            # Process events from QUIC
            event = client._quic.next_event()
            while event is not None:
                if isinstance(event, HandshakeCompleted):
                    logger.info(f"Handshake completed")
                
                elif isinstance(event, StreamDataReceived):
                    logger.info(f"Received response: {event.data.decode()}")
                    response_received = True
                
                elif isinstance(event, ConnectionTerminated):
                    logger.info(f"Connection terminated: {event.error_code}")
                
                event = client._quic.next_event()
            
            # Exit if we got a response
            if response_received:
                break
                
            # Allow time for network IO and event processing
            await asyncio.sleep(0.1)
        
        # Close the connection gracefully
        client._quic.close()
        await asyncio.sleep(0.5)

async def main():
    # Configure SSL key logging for Wireshark
    os.environ["SSLKEYLOGFILE"] = "ssl-keys.log"
    logger.info(f"SSL key logging enabled to {os.environ.get('SSLKEYLOGFILE')}")
    
    # Single connection to server
    logger.info("===== QUIC CONNECTION =====")
    await run_client("quic-server", 8080)
    
    logger.info("Client finished")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)