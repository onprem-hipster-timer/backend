"""
/auth/.well-known/* (OIDC discovery·JWKS) 테스트

실제 앱에 붙여 `/auth/{path:path}` Kratos 프록시보다 먼저 매칭되는지도 함께 확인한다.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import oidc_discovery
from app.core.config import Settings
from app.main import app

ISSUER = "https://api.example.com/auth/"
JWKS = {"keys": [{"kty": "EC", "crv": "P-256", "kid": "k1", "alg": "ES256", "use": "sig", "x": "x", "y": "y"}]}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(
        oidc_discovery, "settings", Settings(OIDC_ISSUER_URL=ISSUER, OIDC_JWKS=json.dumps(JWKS))
    )


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(oidc_discovery, "settings", Settings(OIDC_ISSUER_URL=ISSUER, OIDC_JWKS=""))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("path", ["/auth/.well-known/jwks.json", "/auth//.well-known/jwks.json"])
def test_jwks_served_with_cache_header(configured, client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == JWKS
    assert response.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.parametrize(
    "path", ["/auth/.well-known/openid-configuration", "/auth//.well-known/openid-configuration"]
)
def test_openid_configuration_points_to_jwks(configured, client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    document = response.json()
    assert document["issuer"] == ISSUER
    assert document["jwks_uri"] == "https://api.example.com/auth/.well-known/jwks.json"
    assert document["id_token_signing_alg_values_supported"] == ["ES256"]


@pytest.mark.parametrize("path", [
    "/auth/.well-known/jwks.json",
    "/auth/.well-known/openid-configuration",
    "/auth//.well-known/jwks.json",
])
def test_not_found_without_jwks(unconfigured, client, path):
    assert client.get(path).status_code == 404


def test_openid_configuration_not_found_without_issuer(monkeypatch, client):
    monkeypatch.setattr(
        oidc_discovery, "settings", Settings(OIDC_ISSUER_URL="", OIDC_JWKS=json.dumps(JWKS))
    )

    assert client.get("/auth/.well-known/openid-configuration").status_code == 404
