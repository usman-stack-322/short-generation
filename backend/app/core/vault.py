"""Authenticated encryption at rest; the key never resides in the database."""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings


def cipher():
    key = settings.token_encryption_key or base64.urlsafe_b64encode(
        hashlib.sha256((settings.app_secret_key + ':oauth-vault-v1').encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()
