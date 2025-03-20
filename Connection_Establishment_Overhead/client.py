import asyncio
import json
import logging
import os
import ssl
import time
from datetime import datetime, timezone
from typing import Optional

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, StreamDataReceived, ConnectionTerminated
from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import SessionTicket

# Configure logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("client")

# Global variable to store the most recently received session ticket
saved_session_ticket = None

def load_saved_session_ticket():
    """Load a saved session ticket."""
    try:
        with open("/app/session-tickets/session_ticket.json", "r") as f:
            ticket_data = json.load(f)
            
            # Create a new SessionTicket with all required fields
            ticket = SessionTicket(
                ticket=bytes.fromhex(ticket_data["ticket"]),
                age_add=ticket_data["age_add"],
                cipher_suite=ticket_data["cipher_suite"],
                not_valid_after=datetime.fromtimestamp(ticket_data["not_valid_after"], tz=timezone.utc),
                not_valid_before=datetime.fromtimestamp(ticket_data["not_valid_before"], tz=timezone.utc),
                resumption_secret=bytes.fromhex(ticket_data["resumption_secret"]),
                server_name=ticket_data["server_name"]
            )
            
            # Check if ticket is still valid using timezone-aware comparison
            now = datetime.now(timezone.utc)
            if now < ticket.not_valid_after and now >= ticket.not_valid_before:
                logger.info(f"Loaded saved session ticket from /app/session-tickets/session_ticket.json (size: {len(ticket.ticket)} bytes)")
                return ticket
            else:
                logger.warning("Saved session ticket is expired or not yet valid")
                return None
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Failed to load session ticket: {e}")
        return None

def session_ticket_handler(ticket: SessionTicket) -> None:
    """Save a new session ticket."""
    logger.info(f"✓ NEW SESSION TICKET RECEIVED: {len(ticket.ticket)} bytes")
    
    # Save all session ticket fields
    os.makedirs("/app/session-tickets", exist_ok=True)
    with open("/app/session-tickets/session_ticket.json", "w") as f:
        ticket_data = {
            "ticket": ticket.ticket.hex(),
            "age_add": ticket.age_add,
            "cipher_suite": ticket.cipher_suite,
            "not_valid_after": ticket.not_valid_after.astimezone(timezone.utc).timestamp(),
            "not_valid_before": ticket.not_valid_before.astimezone(timezone.utc).timestamp(),
            "resumption_secret": ticket.resumption_secret.hex(),
            "server_name": ticket.server_name,
            "timestamp": time.time()
        }
        json.dump(ticket_data, f)
        logger.info(f"Session ticket saved to /app/session-tickets/session_ticket.json (size: {len(ticket.ticket)} bytes)")

async def run_client(host, port, *, use_saved_ticket=True):
    """Create and run a QUIC client connection."""
    # Create QUIC configuration
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        verify_mode=ssl.CERT_NONE,
        quic_logger=QuicFileLogger("./qlogs")
    )

    # Load certificate
    configuration.load_verify_locations("certs/ssl_cert.pem")
    
    # Try to load saved session ticket
    if use_saved_ticket:
        saved_ticket = load_saved_session_ticket()
        if saved_ticket:
            logger.info("Attempting connection with saved session ticket")
            configuration.session_ticket = saved_ticket
            configuration.enable_early_data = True
            configuration.max_early_data = 0xffffffff
            configuration.cipher_suites = [saved_ticket.cipher_suite]  # Use the same cipher suite
    
    # Connect to the server
    try:
        async with connect(
            host,
            port,
            configuration=configuration,
            session_ticket_handler=session_ticket_handler,
            wait_connected=True
        ) as client:
            # Send message
            message = f"Hello from QUIC client at {time.time()}"
            
            # Get current time for RTT measurement
            start_time = time.time()
            
            # Send data on a new stream
            stream_id = client._quic.get_next_available_stream_id()
            client._quic.send_stream_data(stream_id, message.encode())
            logger.info(f"Sent message: {message}")
            
            # Wait for the response and events
            response_received = False
            handshake_done = False
            
            # Try for 5 seconds
            while time.time() - start_time < 5:
                event = client._quic.next_event()
                while event is not None:
                    if isinstance(event, HandshakeCompleted):
                        handshake_done = True
                        logger.info("===== Handshake Details =====")
                        logger.info(f"Session resumed: {event.session_resumed}")
                        logger.info(f"Early data accepted: {getattr(event, 'early_data_accepted', False)}")
                        logger.info("==========================")
                    
                    elif isinstance(event, StreamDataReceived):
                        end_time = time.time()
                        rtt = (end_time - start_time) * 1000  # Convert to milliseconds
                        logger.info(f"Received response: {event.data.decode()}")
                        logger.info(f"Round-trip time: {rtt:.2f}ms")
                        response_received = True
                    
                    elif isinstance(event, ConnectionTerminated):
                        logger.info(f"Connection terminated: {event.error_code}")
                    
                    event = client._quic.next_event()
                
                if response_received and handshake_done:
                    break
                
                await asyncio.sleep(0.1)
            
            # Close connection gracefully
            client._quic.close()
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise

async def main():
    # Configure SSL key logging for Wireshark
    if "SSLKEYLOGFILE" in os.environ:
        logging.info("SSL key logging enabled to %s", os.environ["SSLKEYLOGFILE"])
        
    # First connection (1-RTT)
    logger.info("\n===== FIRST CONNECTION (1-RTT) =====")
    await run_client("quic-server", 8080, use_saved_ticket=False)
    
    # Wait before attempting resumption
    logger.info("Waiting 2 seconds before attempting resumption...")
    await asyncio.sleep(2)
    
    # Second connection (attempting 0-RTT)
    logger.info("\n===== SECOND CONNECTION (attempting 0-RTT) =====")
    await run_client("quic-server", 8080, use_saved_ticket=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass