import base64
import hashlib
import os
import platform
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_machine_fingerprint() -> str:
    node = uuid.getnode()
    hostname = platform.node()
    raw = f"{node}:{hostname}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _derive_key() -> bytes:
    fingerprint = _get_machine_fingerprint()
    return hashlib.sha256(f"LamImager:{fingerprint}".encode()).digest()


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("ascii")


def decrypt(ciphertext_b64: str) -> str:
    if not ciphertext_b64:
        return ""
    key = _derive_key()
    combined = base64.b64decode(ciphertext_b64)
    nonce = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def mask_key(key: str) -> str:
    if not key or len(key) <= 4:
        return "****"
    return "****" + key[-4:]
