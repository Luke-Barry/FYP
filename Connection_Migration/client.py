import asyncio
import ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )

    async with connect(host, port, configuration=configuration) as client:
        print("Connection established with server.")

        # Open a single stream and send data periodically
        stream_id = client._quic.get_next_available_stream_id()
        for i in range(10):
            message = f"Hello from QUIC client! Message {i+1}"
            client._quic.send_stream_data(stream_id, message.encode(), end_stream=False)
            print(f"Sent: {message}")
            await asyncio.sleep(5)  # Wait before sending the next message

        print("All messages sent. Closing connection.")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080

    asyncio.run(run_client(host, port))
