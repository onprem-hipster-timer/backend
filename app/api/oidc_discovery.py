"""
OIDC discovery와 JWKS

Kratos가 서명하는 JWT를 backend 밖(실시간 Worker 등)에서도 검증할 수 있게
OIDC_JWKS 공개 키와 최소 discovery 문서를 인증 없이 내준다.

- OIDC_JWKS가 비어 있으면 404
- 발급자(OIDC_ISSUER_URL)가 `/`로 끝나므로 이어 붙인 `/auth//.well-known/...` 경로도 받는다
- `/auth/{path:path}` Kratos 프록시보다 먼저 등록해야 한다 (app/main.py)
"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings

CACHE_CONTROL = "public, max-age=3600"

router = APIRouter(include_in_schema=False)


def _jwks() -> dict:
    if not settings.OIDC_JWKS:
        raise HTTPException(status_code=404)
    return json.loads(settings.OIDC_JWKS)


@router.get("/auth/.well-known/jwks.json")
@router.get("/auth//.well-known/jwks.json")
def jwks() -> JSONResponse:
    return JSONResponse(_jwks(), headers={"Cache-Control": CACHE_CONTROL})


@router.get("/auth/.well-known/openid-configuration")
@router.get("/auth//.well-known/openid-configuration")
def openid_configuration() -> JSONResponse:
    keys = _jwks()["keys"]
    if not settings.OIDC_ISSUER_URL:
        raise HTTPException(status_code=404)
    base = settings.OIDC_ISSUER_URL.rstrip("/")
    document = {
        "issuer": settings.OIDC_ISSUER_URL,
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "response_types_supported": ["id_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": sorted({k["alg"] for k in keys if "alg" in k}),
    }
    return JSONResponse(document, headers={"Cache-Control": CACHE_CONTROL})
