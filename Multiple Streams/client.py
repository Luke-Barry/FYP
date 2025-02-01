import asyncio
import ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

async def handle_stream_messages(writer, stream_id):
    """Send messages on a specific stream."""
    try:
        for i in range(10):
            message = f"Hello from Stream {stream_id}! Message {i+1}"
            writer.write(message.encode())
            await writer.drain()
            print(f"Stream {stream_id} sent: {message}")
            await asyncio.sleep(1)  # Wait between messages
            
        print(f"Stream {stream_id}: All messages sent")
        
        # Signal end of stream without explicit close
        writer.write_eof()
        
    except Exception as e:
        print(f"Stream {stream_id} error: {e}")

async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )

    async with connect(host, port, configuration=configuration) as protocol:
        print("Connection established with server.")

        # Create three separate bidirectional streams
        streams = []
        for i in range(3):
            reader, writer = await protocol.create_stream(is_unidirectional=False)
            streams.append(handle_stream_messages(writer, i + 1))

        try:
            # Send messages on all streams concurrently
            await asyncio.gather(*streams)
            print("All streams completed successfully")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))