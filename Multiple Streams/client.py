import asyncio
import ssl
from asyncio import Queue
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

# Define stream IDs for each queue
STREAM_IDS = {
    'queue1': 0,
    'queue2': 2,
    'queue3': 8
}

async def send_from_queue(protocol, queue: Queue, queue_name: str):
    """Send messages from a queue on its dedicated stream ID."""
    stream_id = STREAM_IDS[queue_name]
    
    try:
        # Create a stream with specific ID
        reader, writer = await protocol.create_stream()
        print(f"Created stream {stream_id} for {queue_name}")
        
        while True:
            try:
                message = await queue.get()
                if message is None:  # Sentinel value to stop
                    break
                    
                # Acquire lock to ensure sequential transmission
                async with protocol._sender_lock:
                    writer.write(message.encode())
                    await writer.drain()
                    print(f"Sent on stream {stream_id}: {message}")
                    await asyncio.sleep(1)  # Delay between messages
                
            except asyncio.QueueEmpty:
                continue
                
        print(f"Queue {queue_name} on stream {stream_id} finished")
        writer.write_eof()
        
    except Exception as e:
        print(f"Error on stream {stream_id}: {e}")

async def run_client(host: str, port: int) -> None:
    # Create message queues
    queues = {
        'queue1': Queue(),
        'queue2': Queue(),
        'queue3': Queue()
    }
    
    # Populate queues with messages
    for i in range(5):
        for queue_name, queue in queues.items():
            await queue.put(f"Message {i+1} from {queue_name}")
    
    # Add sentinel values to mark end of queues
    for queue in queues.values():
        await queue.put(None)

    configuration = QuicConfiguration(
        alpn_protocols=["quic-demo"],
        is_client=True,
        max_datagram_frame_size=65536,
        secrets_log_file=open("/app/certs/ssl_keylog.txt", "a"),
        verify_mode=ssl.CERT_NONE
    )

    async with connect(host, port, configuration=configuration) as protocol:
        # Add a lock for sequential transmission
        protocol._sender_lock = asyncio.Lock()
        print("Connection established with server.")

        # Create tasks for each queue
        tasks = []
        for queue_name, queue in queues.items():
            task = asyncio.create_task(send_from_queue(protocol, queue, queue_name))
            tasks.append(task)

        try:
            # Wait for all queues to be processed
            await asyncio.gather(*tasks)
            print("All streams completed successfully")
            
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

if __name__ == "__main__":
    host = "quic-server"
    port = 8080
    asyncio.run(run_client(host, port))