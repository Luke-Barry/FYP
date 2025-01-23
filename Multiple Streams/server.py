import asyncio
import logging
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

class QuicServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            logger.info(f"Received on stream {event.stream_id}: {event.data.decode()}")
            if event.end_stream:
                logger.info(f"Stream {event.stream_id} closed.")

async def main():
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )

    # Load SSL certificate and private key
    configuration.load_cert_chain("/app/certs/ssl_cert.pem", "/app/certs/ssl_key.pem")

    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        create_protocol=QuicServerProtocol,
    )

    logger.info("Server started on 0.0.0.0:8080")
    await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
