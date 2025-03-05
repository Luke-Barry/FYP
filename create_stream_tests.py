import os
import shutil

# Base directory
base_dir = os.path.dirname(os.path.abspath(__file__))

# Stream configurations to test
stream_counts = [1, 3, 5, 10, 50, 100]

# Files to copy and modify
files_to_copy = [
    'client.py',
    'server.py',
    'Docker-compose.yml',
    'client.Dockerfile',
    'server.Dockerfile',
    'requirements.txt'
]

def create_test_directory(stream_count):
    # Create directory
    dir_name = f'Multiple_Streams_{stream_count}'
    dir_path = os.path.join(base_dir, dir_name)
    
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    
    os.makedirs(dir_path)
    os.makedirs(os.path.join(dir_path, 'qlogs'))
    
    # Copy files
    for file in files_to_copy:
        src = os.path.join(base_dir, 'Multiple_Streams_3', file)
        dst = os.path.join(dir_path, file)
        shutil.copy2(src, dst)
        
        # Modify client.py for the number of streams
        if file == 'client.py':
            with open(dst, 'r') as f:
                content = f.read()
            
            # Update the number of queues
            content = content.replace(
                "queues = {f'queue{i}': Queue() for i in range(1, 4)}",
                f"queues = {{f'queue{{i}}': Queue() for i in range(1, {stream_count + 1})}}"
            )
            
            with open(dst, 'w') as f:
                f.write(content)

def rename_current_directory():
    current_dir = os.path.join(base_dir, 'Multiple_Streams')
    if os.path.exists(current_dir):
        new_dir = os.path.join(base_dir, 'Multiple_Streams_3')
        if os.path.exists(new_dir):
            shutil.rmtree(new_dir)
        os.rename(current_dir, new_dir)

def main():
    # First rename the current Multiple_Streams directory
    rename_current_directory()
    
    # Create test directories for each stream count
    for count in stream_counts:
        create_test_directory(count)
        print(f"Created test directory for {count} streams")

if __name__ == "__main__":
    main()
