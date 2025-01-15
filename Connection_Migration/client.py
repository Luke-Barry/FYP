import asyncio
import logging
from typing import Optional
import ssl
import os

from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
from aioquic.tls import SessionTicket

logger = logging.getLogger("client")
logging.basicConfig(level=logging.INFO)

# Set the SSL keylog file environment variable
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

class QuicClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._streaming = False
        self._messages_sent = 0

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            logger.info(f"Received response: {event.data.decode()}")

async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        verify_mode=ssl.CERT_NONE,  # Don't verify self-signed cert
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=QuicClientProtocol,
    ) as client:
        # Send a message
        stream_id = client._quic.get_next_available_stream_id()
        message = "Hello from QUIC client!"
        logger.info(f"Sending: {message}")
        client._quic.send_stream_data(stream_id, message.encode(), end_stream=True)
        
        # Wait for a while to ensure message is received and processed
        await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_client("172.16.238.11", 8080))
    except KeyboardInterrupt:
        pass