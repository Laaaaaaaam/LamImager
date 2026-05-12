import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import encrypt, decrypt, _derive_key
import hashlib

key = _derive_key()
print(f"Current key: {key.hex()[:32]}...")

# Test: encrypt and decrypt a known value
test_val = "sk-test-1234567890abcdef"
encrypted = encrypt(test_val)
decrypted = decrypt(encrypted)
print(f"Roundtrip: {'OK' if decrypted == test_val else 'FAIL'}")
print(f"  encrypted length: {len(encrypted)}")

# Now try to understand why the DB values fail
# The DB values were encrypted with a DIFFERENT key
# Let's check if there's a different Python environment that might have been used

import uuid
import platform

node = uuid.getnode()
hostname = platform.node()
fingerprint = hashlib.sha256(f"{node}:{hostname}".encode()).hexdigest()
derived = hashlib.sha256(f"LamImager:{fingerprint}".encode()).digest()
print(f"\nMachine fingerprint components:")
print(f"  MAC: {node}")
print(f"  Hostname: {hostname}")
print(f"  Fingerprint: {fingerprint[:32]}...")
print(f"  Derived key: {derived.hex()[:32]}...")

# Check if the key matches
print(f"  Key match: {key == derived}")
