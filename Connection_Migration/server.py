import asyncio
import logging
from typing import Dict, Optional
import ssl
import os

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived
from aioquic.tls import SessionTicket

logger = logging.getLogger("server")
logging.basicConfig(level=logging.INFO)

# Set the SSL keylog file environment variable
os.environ['SSLKEYLOGFILE'] = '/app/certs/ssl_keylog.txt'

class QuicServerProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._streams: Dict[int, asyncio.Queue[StreamDataReceived]] = {}

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            logger.info(f"Received data: {event.data.decode()}")
            # Echo the data back without closing the stream
            self._quic.send_stream_data(event.stream_id, event.data, end_stream=False)

async def main():
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=False,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a")
    )

    # Load SSL certificate and private key
    configuration.load_cert_chain("certs/ssl_cert.pem", "certs/ssl_key.pem")

    server = await serve(
        host="0.0.0.0",
        port=8080,
        configuration=configuration,
        create_protocol=QuicServerProtocol,
    )

    logger.info("Server started on 0.0.0.0:8080")
    await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
