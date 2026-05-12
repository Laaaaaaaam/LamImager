import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import _get_machine_fingerprint, _derive_key
import uuid
import platform

node = uuid.getnode()
hostname = platform.node()
fingerprint = _get_machine_fingerprint()
key = _derive_key()

print(f"MAC: {node}")
print(f"Hostname: {hostname}")
print(f"Fingerprint: {fingerprint[:16]}...")
print(f"Key (hex): {key.hex()[:16]}...")
