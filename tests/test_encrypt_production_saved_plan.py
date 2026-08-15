import base64

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.encrypt_production_saved_plan import (
    MAGIC,
    PlanEncryptionError,
    encrypt_plan,
)


def test_saved_plan_envelope_is_authenticated_and_decryptable():
    key = bytes(range(32))
    nonce = bytes(range(12))
    encrypted = encrypt_plan(
        plaintext=b"sensitive terraform plan",
        key_b64=base64.b64encode(key).decode(),
        nonce=nonce,
    )
    assert encrypted.startswith(MAGIC + nonce)
    assert (
        AESGCM(key).decrypt(nonce, encrypted[len(MAGIC) + 12 :], MAGIC)
        == b"sensitive terraform plan"
    )


def test_saved_plan_encryption_rejects_invalid_key_and_tamper():
    with pytest.raises(PlanEncryptionError):
        encrypt_plan(plaintext=b"plan", key_b64=base64.b64encode(b"short").decode())
    key = bytes(range(32))
    nonce = bytes(range(12))
    encrypted = bytearray(
        encrypt_plan(
            plaintext=b"plan",
            key_b64=base64.b64encode(key).decode(),
            nonce=nonce,
        )
    )
    encrypted[-1] ^= 1
    with pytest.raises(InvalidTag):
        AESGCM(key).decrypt(nonce, bytes(encrypted[len(MAGIC) + 12 :]), MAGIC)
