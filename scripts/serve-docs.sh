#!/usr/bin/env bash
# 로컬 문서 서버 실행 (openapi.json 생성 후 mkdocs serve)
# 사용: ./scripts/serve-docs.sh

set -e
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

echo "Generating docs/api/openapi.json..."
OIDC_ENABLED=false DATABASE_URL="sqlite:///:memory:" python -c "
import os
os.environ['OIDC_ENABLED'] = 'false'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app.main import app
import json
with open('docs/api/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
print('openapi.json generated.')
"

echo "Starting mkdocs serve..."
exec python -m mkdocs serve "$@"
