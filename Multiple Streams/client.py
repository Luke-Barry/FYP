import asyncio
import ssl
from asyncio import Queue
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

async def send_from_queue(protocol, queue: Queue, queue_name: str):
    """Send messages from a queue on its dedicated stream."""
    try:
        # Create a new stream.
        reader, writer = await protocol.create_stream()
        stream_id = writer.get_extra_info("stream_id")
        print(f"Created stream {stream_id} for {queue_name}")
        
        while True:
            message = await queue.get()
            if message is None:  # Sentinel value to stop sending on this stream.
                break
                    
            # Use a lock to ensure sequential transmission.
            async with protocol._sender_lock:
                writer.write(message.encode())
                await writer.drain()
                print(f"Sent on stream {stream_id}: {message}")
                await asyncio.sleep(0.1)  # Small delay between messages
                
        print(f"Queue {queue_name} on stream {stream_id} finished")
        # Do not call writer.write_eof() so that the stream (and connection) remains open.
        
    except Exception as e:
        print(f"Error on stream {stream_id}: {e}")

async def run_client(host: str, port: int) -> None:
    # Create a message queue for each channel.
    queues = {
        'queue1': Queue(),
        'queue2': Queue(),
        'queue3': Queue()
    }
    
    # Populate the queues with messages.
    for i in range(5):
        for queue_name, queue in queues.items():
            await queue.put(f"Message {i+1} from {queue_name}")
    
    # Add a sentinel (None) to each queue to mark the end.
    for queue in queues.values():
        await queue.put(None)

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )
    configuration.max_streams_bidi = 100

    async with connect(host, port, configuration=configuration) as protocol:
        protocol._sender_lock = asyncio.Lock()
        print("Connection established with server.")

        # Create a send task for each queue.
        tasks = []
        for queue_name, queue in queues.items():
            task = asyncio.create_task(send_from_queue(protocol, queue, queue_name))
            tasks.append(task)

        try:
            await asyncio.gather(*tasks)
            print("All streams completed successfully")
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))
