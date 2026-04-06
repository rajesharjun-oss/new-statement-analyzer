import sys
import os

log_path = 'verif_log.txt'
if not os.path.exists(log_path):
    print(f"Log file {log_path} not found.")
    sys.exit(1)

try:
    with open(log_path, 'rb') as f:
        raw = f.read()
        content = raw.decode('utf-16', errors='ignore')
except Exception as e:
    print(f"Failed to decode log: {e}")
    sys.exit(1)

print(content)
