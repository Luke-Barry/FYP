import asyncio
import logging
import os
import ssl
import pickle
from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
from aioquic.quic.logger import QuicFileLogger

logger = logging.getLogger("client")
logging.basicConfig(level=logging.INFO)

# Set the SSL keylog file environment variable
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

class QuicClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            logger.info(f"Received response: {event.data.decode()}")

def save_session_ticket(ticket):
    """Save the session ticket for 0-RTT connection."""
    with open("/app/certs/session_ticket.pkl", "wb") as f:
        pickle.dump(ticket, f)

def load_session_ticket():
    """Load a saved session ticket if available."""
    try:
        with open("/app/certs/session_ticket.pkl", "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return None

async def establish_connection(host: str, port: int, session_ticket=None) -> None:
    qlog_dir = "/app/qlogs"
    os.makedirs(qlog_dir, exist_ok=True)  # Ensure qlog directory exists
    quic_logger = QuicFileLogger(qlog_dir)  # Pass directory, NOT file path

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE,
        session_ticket_handler=save_session_ticket,
        quic_logger=quic_logger
    )

    if session_ticket:
        configuration.session_ticket = session_ticket
        logger.info("Attempting 0-RTT connection with saved session ticket")
    else:
        logger.info("Performing initial 1-RTT connection")

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=QuicClientProtocol,
    ) as client:
        logger.info("QUIC connection established")
        stream_id = client._quic.get_next_available_stream_id()
        client._quic.send_stream_data(stream_id, b"Test message")
        await asyncio.sleep(1)

async def run_client(host: str, port: int) -> None:
    # Initial connection (1-RTT)
    logger.info("Performing initial connection (1-RTT)")
    await establish_connection(host, port)
    
    # Wait briefly to ensure session ticket is saved
    await asyncio.sleep(2)
    
    # Load saved session ticket
    session_ticket = load_session_ticket()
    if session_ticket:
        logger.info("Attempting connection resumption (0-RTT)")
        await establish_connection(host, port, session_ticket)
    else:
        logger.error("No session ticket found for 0-RTT connection")

if __name__ == "__main__":
    try:
        asyncio.run(run_client("quic-server", 8080))
    except KeyboardInterrupt:
        pass
