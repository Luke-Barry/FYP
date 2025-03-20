import asyncio
import logging
import os
import ssl
import time
from typing import Dict, Optional, Callable

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted, ConnectionTerminated
from aioquic.quic.logger import QuicFileLogger
from aioquic.tls import SessionTicket

# Configure logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("server")

# Create directories for logs and certs
os.makedirs("./qlogs", exist_ok=True)
os.makedirs("./certs", exist_ok=True)

# Store session tickets
session_tickets: Dict[bytes, SessionTicket] = {}

class QuicServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ack_waiter: Optional[asyncio.Future[None]] = None

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            logger.info(
                f"Handshake completed for connection {self._quic.host_cid.hex()}: "
                f"resumed={event.session_resumed}, "
                f"early_data={getattr(event, 'early_data_accepted', False)}"
            )

        if isinstance(event, StreamDataReceived):
            data = event.data.decode()
            logger.info(f"Received: {data}")
            
            # Echo it back
            response = f"Echoed back: {data}"
            self._quic.send_stream_data(event.stream_id, response.encode())
            logger.info(f"Echoed back: {data}")

        elif isinstance(event, ConnectionTerminated):
            if hasattr(self._quic, 'host_cid'):
                logger.info(f"Connection {self._quic.host_cid.hex()} terminated")
            if self._ack_waiter is not None:
                self._ack_waiter.set_result(None)

def save_session_ticket(ticket: SessionTicket) -> None:
    """Save a new session ticket."""
    if not ticket or not hasattr(ticket, 'ticket') or not ticket.ticket:
        logger.warning("Invalid session ticket received")
        return False

    session_tickets[ticket.ticket] = ticket
    logger.info(f"New session ticket issued (size: {len(ticket.ticket)} bytes)")
    return True

def lookup_session_ticket(ticket_bytes: bytes) -> Optional[SessionTicket]:
    """Look up a ticket in the session ticket store."""
    ticket = session_tickets.get(ticket_bytes)
    if ticket:
        logger.info(f"Found existing session ticket for resumption")
        return ticket
    return None

async def run_server():
    # Configure SSL key logging
    os.environ["SSLKEYLOGFILE"] = "ssl-keys.log"
    logger.info(f"SSL key logging enabled to {os.environ.get('SSLKEYLOGFILE')}")

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        quic_logger=QuicFileLogger("./qlogs"),
    )

    # Load SSL certificate and private key
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")

    # Enable TLS 1.3 and session ticket issuance with proper settings
    configuration.ticket_lifetime = 24 * 3600  # 24 hours validity
    configuration.verify_mode = ssl.CERT_NONE
    configuration.cipher_suites = [0x1301]  # TLS_AES_128_GCM_SHA256
    configuration.enable_early_data = True  # Enable 0-RTT
    configuration.max_early_data = 0xffffffff  # Maximum early data size
    
    logger.info("QUIC server started on 0.0.0.0:8080")
    
    await serve(
        "0.0.0.0",
        8080,
        configuration=configuration,
        create_protocol=QuicServerProtocol,
        session_ticket_fetcher=lookup_session_ticket,
        session_ticket_handler=save_session_ticket,
        retry=False  # Disable address validation which can interfere with 0-RTT
    )

    try:
        await asyncio.Future()  # run forever
    finally:
        logger.info("Server shutting down")

if __name__ == "__main__":
    try:
        # Configure SSL key logging for Wireshark
        if "SSLKEYLOGFILE" in os.environ:
            logging.info("SSL key logging enabled to %s", os.environ["SSLKEYLOGFILE"])
            
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
