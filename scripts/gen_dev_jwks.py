"""
로컬 Kratos(compose.kratos.yaml)용 ES256 서명 키 생성

- 개인 JWKS: dev/kratos/jwks.private.json (git 무시, Kratos tokenizer가 서명에 사용)
- 공개 JWKS: 표준 출력 (backend OIDC_JWKS에 넣는다)

운영 키는 infra README의 step CLI 절차로 만든다. 이 스크립트는 로컬 전용이다.
"""
import json
import pathlib

from joserfc.jwk import ECKey

PRIVATE_JWKS = pathlib.Path(__file__).resolve().parent.parent / "dev" / "kratos" / "jwks.private.json"

key = ECKey.generate_key("P-256", parameters={"kid": "dev", "alg": "ES256", "use": "sig"}, private=True)
PRIVATE_JWKS.write_text(json.dumps({"keys": [key.as_dict(private=True)]}))
print(json.dumps({"keys": [key.as_dict(private=False)]}))
