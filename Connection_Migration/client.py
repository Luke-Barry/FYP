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
        verify_mode=ssl.CERT_NONE  # Skip certificate verification
    )

    async with connect(host, port, configuration=configuration) as protocol:
        print("Connection established with server.")

        # Create a bidirectional stream
        reader, writer = await protocol.create_stream(is_unidirectional=False)

        try:
            for i in range(10):  # Send 10 messages periodically
                message = f"Hello from QUIC client! Message {i+1}"
                writer.write(message.encode())
                await writer.drain()  # Ensure the data is sent
                print(f"Sent: {message}")

                # Wait before sending the next message
                await asyncio.sleep(5)

            print("All messages sent. Closing connection.")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            writer.close()
            await writer.wait_closed()  # Gracefully close the stream

if __name__ == "__main__":
    host = "quic-server"
    port = 8080

    asyncio.run(run_client(host, port))