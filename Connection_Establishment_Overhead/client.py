import asyncio
import logging
import os
import ssl
from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived

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


async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE,  # Don't verify self-signed cert
    )

    # Allow self-signed certificates
    configuration.validate_certificates = False

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=QuicClientProtocol,
    ) as client:
        logger.info("QUIC connection established")
        # Wait briefly to simulate idle time
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(run_client("quic-server", 8080))  # Use the server's container name
    except KeyboardInterrupt:
        pass
