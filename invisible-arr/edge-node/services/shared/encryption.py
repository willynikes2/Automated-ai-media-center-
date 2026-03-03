"""Fernet-based encryption for stored secrets (RD tokens, usenet configs)."""

from functools import lru_cache

from cryptography.fernet import Fernet

from shared.config import get_config


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Return a Fernet instance using ENCRYPTION_KEY from config."""
    config = get_config()
    if not config.encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(config.encryption_key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a string, return base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext, return plaintext."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
