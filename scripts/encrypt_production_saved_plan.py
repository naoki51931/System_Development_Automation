"""Encrypt a Terraform saved plan before it leaves the protected runner."""

import argparse
import base64
import binascii
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"PRODUCTION-TFPLAN-AES256GCM\x00"


class PlanEncryptionError(RuntimeError):
    pass


def encrypt_plan(*, plaintext, key_b64, nonce=None):
    try:
        key = base64.b64decode(key_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise PlanEncryptionError("invalid protected plan encryption key") from exc
    if len(key) != 32:
        raise PlanEncryptionError("plan encryption key must be 32 bytes")
    nonce = nonce or os.urandom(12)
    if len(nonce) != 12:
        raise PlanEncryptionError("AES-GCM nonce must be 12 bytes")
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def write_secure(path, payload):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise PlanEncryptionError("encrypted plan path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".encrypted-plan-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    key = os.environ.get("PRODUCTION_PLAN_ENCRYPTION_KEY_B64", "")
    if not key:
        raise PlanEncryptionError("protected plan encryption key is required")
    if args.input.is_symlink() or not args.input.is_file():
        raise PlanEncryptionError("saved plan input must be a regular file")
    write_secure(
        args.output, encrypt_plan(plaintext=args.input.read_bytes(), key_b64=key)
    )


if __name__ == "__main__":
    main()
