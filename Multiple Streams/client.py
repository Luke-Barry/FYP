import asyncio
import json
import ssl
from asyncio import Queue
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

async def send_from_queue(client, data_queue, stream_name):
    """Send data from a queue to a new stream."""
    # Get a new stream ID for each queue
    stream_id = client._quic.get_next_available_stream_id()
    print(f"{stream_name} Stream ID: {stream_id}")

    while not data_queue.empty():
        data = await data_queue.get()
        client._quic.send_stream_data(stream_id, data.encode(), end_stream=False)
        print(f"Sent on {stream_name} (stream {stream_id}): {data}")
        await asyncio.sleep(1)  # Simulate a small delay between messages

    # Close the stream after all data is sent
    client._quic.send_stream_data(stream_id, b"", end_stream=True)
    print(f"{stream_name} (stream {stream_id}) closed.")

async def run_client(host: str, port: int) -> None:
    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )

    # Initialize data queues
    text_queue = Queue()
    number_queue = Queue()
    json_queue = Queue()

    # Populate the queues
    for i in range(10):  # Text messages
        await text_queue.put(f"Hello from QUIC client! Message {i+1}")
    for i in range(10):  # Lists of integers
        await number_queue.put(json.dumps(list(range(i, i + 5))))  # Example: "[0,1,2,3,4]"
    for i in range(10):  # JSON objects
        await json_queue.put(json.dumps({"message_id": i, "content": f"Sample JSON {i}"}))

    async with connect(host, port, configuration=configuration) as client:
        print("Connection established with server.")

        # Send data concurrently from each queue
        await asyncio.gather(
            send_from_queue(client, text_queue, "Text Queue"),
            send_from_queue(client, number_queue, "Number Queue"),
            send_from_queue(client, json_queue, "JSON Queue"),
        )

        print("All messages sent. Closing connection.")

if __name__ == "__main__":
    host = "quic-server"
    port = 8080

    asyncio.run(run_client(host, port))
