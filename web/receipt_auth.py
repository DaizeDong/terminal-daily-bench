"""Asymmetric authority for replay receipts.

The queue/HTTP process must never possess the worker's private key.  It verifies
an Ed25519 signature against an operator-pinned, read-only public-key registry.
Cryptography runs in-process: no ambient ``PATH`` executable participates in
signing or verification.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Dict

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
except ImportError as exc:  # fail closed; install the explicit ``replay`` extra
    raise RuntimeError(
        "receipt authority requires the terminal-daily-bench[replay] dependencies"
    ) from exc


KEYS_SCHEMA = "terminal-daily-receipt-authorities/v1"
ALGORITHM = "ed25519"
SIGNATURE_DOMAIN = b"terminal-daily-replay-receipt/v2\0"
_KEY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{2,127}$")


class ReceiptAuthorityError(ValueError):
    """The authority configuration or a receipt signature is invalid."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signed_message(body: Dict[str, Any]) -> bytes:
    return SIGNATURE_DOMAIN + canonical_json(body)


def public_key_pem_from_private(private_key: Path) -> str:
    key = private_key.resolve(strict=True)
    if not key.is_file() or private_key.is_symlink():
        raise ReceiptAuthorityError("receipt signing key must be a regular non-symlink file")
    if key.stat().st_mode & 0o077:
        raise ReceiptAuthorityError("receipt signing key permissions must be owner-only")
    try:
        loaded = serialization.load_pem_private_key(key.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise ReceiptAuthorityError("receipt signing key is not valid PEM") from exc
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ReceiptAuthorityError("receipt signing key must be Ed25519")
    return loaded.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def public_key_sha256(public_key_pem: str) -> str:
    try:
        loaded = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise ReceiptAuthorityError("trusted receipt public key is invalid") from exc
    if not isinstance(loaded, Ed25519PublicKey):
        raise ReceiptAuthorityError("trusted receipt public key must be Ed25519")
    der = loaded.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def load_trusted_keys(path: Path) -> Dict[str, Dict[str, str]]:
    """Load a strict public-key registry; no private material is accepted."""
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ReceiptAuthorityError("trusted receipt-key registry is unreadable") from exc
    if path.is_symlink() or not path.is_file() or stat.st_mode & 0o222:
        raise ReceiptAuthorityError(
            "trusted receipt-key registry must be a read-only regular file"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptAuthorityError("trusted receipt-key registry is unreadable") from exc
    if not isinstance(raw, dict) or raw.get("schema") != KEYS_SCHEMA:
        raise ReceiptAuthorityError("unsupported trusted receipt-key registry")
    records = raw.get("keys")
    if not isinstance(records, list) or not records:
        raise ReceiptAuthorityError("trusted receipt-key registry is empty")
    keys: Dict[str, Dict[str, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ReceiptAuthorityError("invalid trusted receipt-key record")
        key_id = record.get("key_id")
        algorithm = record.get("algorithm")
        pem = record.get("public_key_pem")
        expected_sha = record.get("public_key_sha256")
        if not isinstance(key_id, str) or not _KEY_ID_RE.fullmatch(key_id):
            raise ReceiptAuthorityError("invalid trusted receipt key_id")
        if key_id in keys:
            raise ReceiptAuthorityError("duplicate trusted receipt key_id")
        if algorithm != ALGORITHM or not isinstance(pem, str) or "PRIVATE KEY" in pem:
            raise ReceiptAuthorityError("trusted registry accepts Ed25519 public keys only")
        actual_sha = public_key_sha256(pem)
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ReceiptAuthorityError("trusted public key lacks its SHA-256 pin")
        if not hmac.compare_digest(actual_sha, expected_sha):
            raise ReceiptAuthorityError("trusted public-key SHA-256 pin mismatch")
        keys[key_id] = {
            "algorithm": algorithm,
            "public_key_pem": pem,
            "public_key_sha256": actual_sha,
        }
    return keys


def sign_body(body: Dict[str, Any], *, private_key: Path, key_id: str,
              trusted_keys: Path) -> Dict[str, str]:
    """Sign with a worker-only key and prove it matches the pinned public key."""
    keys = load_trusted_keys(trusted_keys)
    if key_id not in keys:
        raise ReceiptAuthorityError("receipt signing key_id is not trusted")
    derived_pem = public_key_pem_from_private(private_key)
    if not hmac.compare_digest(
        public_key_sha256(derived_pem), keys[key_id]["public_key_sha256"]
    ):
        raise ReceiptAuthorityError("receipt private key does not match pinned public key")
    try:
        loaded = serialization.load_pem_private_key(
            private_key.resolve().read_bytes(), password=None,
        )
    except (OSError, ValueError, TypeError) as exc:
        raise ReceiptAuthorityError("receipt signing key is not valid PEM") from exc
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ReceiptAuthorityError("receipt signing key must be Ed25519")
    signature = loaded.sign(signed_message(body))
    return {
        "algorithm": ALGORITHM,
        "key_id": key_id,
        "value": base64.b64encode(signature).decode("ascii"),
    }


def verify_body(body: Dict[str, Any], signature: Dict[str, Any], *,
                trusted_keys: Path) -> None:
    if not isinstance(signature, dict):
        raise ReceiptAuthorityError("receipt has no authority signature")
    key_id = signature.get("key_id")
    if signature.get("algorithm") != ALGORITHM or not isinstance(key_id, str):
        raise ReceiptAuthorityError("receipt signature algorithm/key_id is invalid")
    keys = load_trusted_keys(trusted_keys)
    record = keys.get(key_id)
    if record is None:
        raise ReceiptAuthorityError("receipt key_id is not pinned")
    try:
        raw_signature = base64.b64decode(signature.get("value", ""), validate=True)
    except (TypeError, ValueError) as exc:
        raise ReceiptAuthorityError("receipt signature is not valid base64") from exc
    if len(raw_signature) != 64:
        raise ReceiptAuthorityError("receipt Ed25519 signature has the wrong length")
    try:
        loaded = serialization.load_pem_public_key(
            record["public_key_pem"].encode("ascii")
        )
        if not isinstance(loaded, Ed25519PublicKey):
            raise ReceiptAuthorityError("trusted receipt public key must be Ed25519")
        loaded.verify(raw_signature, signed_message(body))
    except InvalidSignature as exc:
        raise ReceiptAuthorityError(
            "receipt authority signature verification failed"
        ) from exc
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise ReceiptAuthorityError("trusted receipt public key is invalid") from exc


def receipt_sha256(receipt_without_digest: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(receipt_without_digest)).hexdigest()


__all__ = [
    "ALGORITHM", "KEYS_SCHEMA", "ReceiptAuthorityError", "canonical_json",
    "load_trusted_keys", "public_key_pem_from_private", "public_key_sha256",
    "receipt_sha256", "sign_body", "verify_body",
]
