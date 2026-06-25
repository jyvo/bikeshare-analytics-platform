from charset_normalizer import from_path, from_bytes
import os

def detect_encoding(file_path):
    mb_as_bytes = 1024 * 1024
    size_mb = os.path.getsize(file_path) / (mb_as_bytes)

    chunk_size = min(max(int(size_mb * 0.5 * mb_as_bytes), 256 * 1024), 4* mb_as_bytes)

    if size_mb < 1:
        results = from_path(file_path)
    elif size_mb <= 500:
        results = from_path(file_path, chunk_size=chunk_size)
    else:
        with open(file_path, 'rb') as f:
            chunk = f.read(chunk_size)
            results = from_bytes(chunk)
    
    best = results.best()
    if best and best.encoding and best.chaos < 0.2 and best.coherence > 0.7:
        return best.encoding
    return 'utf-8'
