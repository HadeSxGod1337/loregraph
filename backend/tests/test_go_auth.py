"""Tests for the Go-issued access token verifier.

We generate an RSA keypair per test module and sign tokens locally — no
dependency on the Go service, which is the whole point of RS256: the
public key is enough to verify.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from loregraph.api.go_auth import GoMasterAuthenticator

ISSUER = "railroad-auth"
MASTER_ROLE = "master"


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture
def authenticator(tmp_path, keypair):
    _, public_pem = keypair
    key_path = tmp_path / "public.pem"
    key_path.write_bytes(public_pem)
    return GoMasterAuthenticator(
        public_key_pem=public_pem.decode("utf-8"),
        issuer=ISSUER,
        master_role=MASTER_ROLE,
    )


def _sign(private_pem, claims):
    return jwt.encode(claims, private_pem, algorithm="RS256")


def _base_claims(**overrides):
    claims = {
        "sub": "u_1",
        "role": MASTER_ROLE,
        "iss": ISSUER,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


class _FakeRequest:
    def __init__(self, headers):
        self.headers = headers


def _identify(auth, token):
    request = _FakeRequest({"Authorization": f"Bearer {token}"})
    return asyncio.run(auth.identify(request))


def test_master_token_is_accepted(authenticator, keypair):
    private_pem, _ = keypair
    token = _sign(private_pem, _base_claims())
    assert _identify(authenticator, token) is not None


def test_owner_token_is_accepted(authenticator, keypair):
    private_pem, _ = keypair
    token = _sign(private_pem, _base_claims(role="owner"))
    assert _identify(authenticator, token) is not None


def test_non_master_role_is_rejected(authenticator, keypair):
    private_pem, _ = keypair
    token = _sign(private_pem, _base_claims(role="user"))
    assert _identify(authenticator, token) is None


def test_expired_token_is_rejected(authenticator, keypair):
    private_pem, _ = keypair
    token = _sign(
        private_pem,
        _base_claims(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
    )
    assert _identify(authenticator, token) is None


def test_wrong_issuer_is_rejected(authenticator, keypair):
    private_pem, _ = keypair
    token = _sign(private_pem, _base_claims(iss="someone-else"))
    assert _identify(authenticator, token) is None


def test_token_signed_by_another_key_is_rejected(authenticator):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    token = _sign(other_pem, _base_claims())
    assert _identify(authenticator, token) is None


def test_missing_role_claim_is_rejected(authenticator, keypair):
    private_pem, _ = keypair
    claims = _base_claims()
    del claims["role"]
    token = _sign(private_pem, claims)
    assert _identify(authenticator, token) is None


def test_garbage_token_is_rejected(authenticator):
    assert _identify(authenticator, "not-a-jwt") is None


def test_missing_authorization_header_is_rejected(authenticator):
    request = _FakeRequest({})
    assert asyncio.run(authenticator.identify(request)) is None