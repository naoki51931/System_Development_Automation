import uuid
import pytest
from fastapi.testclient import TestClient
from app.api.pagination import decode_cursor, encode_cursor
from app.auth.verifier import LocalAuthProvider, TokenVerificationError
from app.services.storage import LocalArtifactStorage
from app.errors import AppError


def test_jwt_and_cookie_signature_tampering_rejected():
    provider = LocalAuthProvider("quality-secret")
    token = provider.issue("user")
    with pytest.raises(TokenVerificationError):
        provider.verify(token[:-2] + "xx")


def test_cursor_tampering_and_sql_payload_rejected():
    value = encode_cursor(
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        uuid.uuid4(),
    )
    with pytest.raises(Exception):
        decode_cursor(value + "' OR 1=1--")


def test_path_traversal_mime_and_large_file(tmp_path):
    storage = LocalArtifactStorage(tmp_path, max_file_size=4)
    with pytest.raises(AppError):
        storage.put_object("../secret", b"x", "text/plain")
    with pytest.raises(AppError):
        storage.put_object("organizations/x/a", b"x", "image/svg+xml")
    with pytest.raises(AppError):
        storage.put_object("organizations/x/a", b"12345", "text/plain")


def test_open_redirect_and_ssrf_are_not_supported_routes():
    from app.main import create_app

    client = TestClient(create_app())
    assert client.get("/redirect?url=http://169.254.169.254").status_code == 404
    assert client.get("/api/v1/fetch?url=http://169.254.169.254").status_code == 404


def test_security_headers_do_not_expose_details():
    from app.main import create_app

    response = TestClient(create_app()).get("/health")
    assert (
        response.headers["x-frame-options"] == "DENY"
        and response.headers["cache-control"] == "no-store"
    )
    assert "secret" not in response.text.lower()
