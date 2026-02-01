# OIDC 인증 가이드

이 문서는 백엔드 API의 OIDC 인증 시스템에 대한 가이드입니다.

## 1. 인증 아키텍처 개요

이 백엔드는 **OIDC Resource Server (Relying Party)** 로 동작합니다. 
외부 OIDC Provider(Keycloak, Auth0, Google 등)에서 발급한 JWT Access Token을 검증합니다.

### 인증 흐름

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend API
    participant OP as OIDC Provider

    FE->>OP: 1. 로그인 요청
    OP-->>FE: 2. Access Token 발급
    FE->>BE: 3. API 요청 + Bearer Token
    BE->>OP: 4. JWKS 조회 (캐시됨)
    BE->>BE: 5. JWT 서명 검증
    BE-->>FE: 6. 응답 + 사용자 데이터
```

### 핵심 개념

| 용어 | 설명 |
|------|------|
| **OIDC Provider** | 사용자 인증을 담당하는 외부 서버 (Keycloak, Auth0, Google 등) |
| **Access Token** | OIDC Provider가 발급한 JWT, API 요청 시 사용 |
| **JWKS** | JSON Web Key Set, JWT 서명 검증에 사용되는 공개키 |
| **sub claim** | JWT 내 사용자 고유 식별자, 데이터 소유권(owner_id)에 사용 |

### 데이터 격리

모든 사용자 데이터는 `owner_id` 필드로 격리됩니다:
- Schedule, Todo, Tag, Timer 등 모든 모델에 `owner_id` 필드 존재
- `owner_id`는 JWT의 `sub` claim 값과 매칭
- 다른 사용자의 데이터에는 접근 불가 (404 반환)

### 기존 데이터 마이그레이션

마이그레이션 시 기존 데이터에 할당할 `owner_id`를 환경변수로 지정할 수 있습니다:

```bash
# 개발환경 (기본값: test-user-id)
# OIDC_ENABLED=false 시 mock 사용자와 일치하여 기존 데이터에 접근 가능
alembic upgrade head

# 프로덕션 (특정 사용자 ID 지정)
MIGRATION_DEFAULT_OWNER_ID=admin-user-oidc-sub alembic upgrade head
```

| 환경 | MIGRATION_DEFAULT_OWNER_ID | 설명 |
|------|---------------------------|------|
| 개발 | `test-user-id` (기본값) | Mock 사용자와 일치 |
| 프로덕션 | 실제 OIDC sub | 관리자 또는 기존 사용자의 sub claim |

---

## 2. 개발 환경: 인증 비활성화

로컬 개발이나 테스트 시 OIDC 인증을 비활성화할 수 있습니다.

### 방법 1: 환경변수 설정

```bash
# .env 파일
OIDC_ENABLED=false
```

### 방법 2: 환경변수 직접 지정

```bash
# Linux/Mac
OIDC_ENABLED=false uvicorn app.main:app --reload

# Windows (PowerShell)
$env:OIDC_ENABLED="false"; uvicorn app.main:app --reload
```

### 인증 비활성화 시 동작

인증이 비활성화되면 모든 요청에 아래의 **Mock 사용자**가 자동으로 주입됩니다:

```json
{
  "sub": "test-user-id",
  "email": "test@example.com",
  "name": "Test User"
}
```

!!! warning "주의"
    프로덕션 환경에서는 반드시 `OIDC_ENABLED=true`로 설정하세요!

### 테스트 환경

pytest 실행 시 자동으로 인증이 비활성화됩니다 (`tests/conftest.py`에서 설정):

```python
import os
os.environ["OIDC_ENABLED"] = "false"
```

---

## 3. 프로덕션: OIDC 설정

### 환경변수 목록

| 환경변수 | 필수 | 기본값 | 설명 |
|----------|------|--------|------|
| `OIDC_ENABLED` | O | `true` | 인증 활성화 여부 |
| `OIDC_ISSUER_URL` | O | - | OIDC Provider의 Issuer URL |
| `OIDC_AUDIENCE` | O | - | Client ID (Access Token의 `aud` claim) |
| `OIDC_DISCOVERY_URL` | X | 자동 생성 | 커스텀 Discovery URL |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | X | `3600` | JWKS 캐시 TTL (초) |

### 예시 설정 (.env)

```bash
# 프로덕션 설정 예시
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://auth.example.com/realms/production
OIDC_AUDIENCE=my-frontend-app
OIDC_JWKS_CACHE_TTL_SECONDS=3600
```

### Docker Compose 설정

```yaml
# compose.yaml
services:
  backend:
    environment:
      - OIDC_ENABLED=true
      - OIDC_ISSUER_URL=https://auth.example.com/realms/production
      - OIDC_AUDIENCE=my-frontend-app
```

---

## 4. Well-Known 엔드포인트

### 자동 Discovery

백엔드는 OIDC Discovery를 통해 자동으로 Provider 설정을 가져옵니다:

```
Discovery URL = {OIDC_ISSUER_URL}/.well-known/openid-configuration
```

예시:
- Issuer URL: `https://auth.example.com/realms/myrealm`
- Discovery URL: `https://auth.example.com/realms/myrealm/.well-known/openid-configuration`

### 커스텀 Discovery URL

비표준 경로를 사용하는 Provider의 경우 직접 지정:

```bash
OIDC_DISCOVERY_URL=https://auth.example.com/custom/.well-known/openid-configuration
```

### Discovery에서 가져오는 정보

| 필드 | 용도 |
|------|------|
| `jwks_uri` | JWT 서명 검증을 위한 공개키 URL |
| `issuer` | 토큰 발급자 검증용 |

### JWKS 캐싱

성능 최적화를 위해 JWKS는 캐싱됩니다:
- 기본 캐시 TTL: 3600초 (1시간)
- `OIDC_JWKS_CACHE_TTL_SECONDS` 환경변수로 조정 가능
- 캐시 만료 시 자동으로 재조회

---

## 5. 프론트엔드 통합 가이드

### 인증 헤더 형식

모든 API 요청에 Bearer 토큰을 포함해야 합니다:

```
Authorization: Bearer <access_token>
```

### REST API 요청 예시

#### JavaScript (fetch)

```javascript
const accessToken = 'your-access-token';

const response = await fetch('http://localhost:8000/api/v1/schedules', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
});

if (response.status === 401) {
  // 토큰 만료 또는 유효하지 않음 → 재로그인 필요
  redirectToLogin();
}

const data = await response.json();
```

#### Axios 인터셉터

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
});

// 요청 인터셉터: 토큰 자동 추가
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터: 401 처리
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 토큰 갱신 또는 재로그인
      handleTokenRefresh();
    }
    return Promise.reject(error);
  }
);
```

### GraphQL 요청 예시

```javascript
const query = `
  query GetCalendar($startDate: Date!, $endDate: Date!) {
    calendar(startDate: $startDate, endDate: $endDate) {
      days {
        date
        events {
          id
          title
        }
      }
    }
  }
`;

const response = await fetch('http://localhost:8000/graphql', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query,
    variables: {
      startDate: '2026-01-01',
      endDate: '2026-01-31',
    },
  }),
});
```

### 에러 응답 처리

#### 401 Unauthorized

```json
{
  "detail": "Authorization header missing"
}
```
또는
```json
{
  "detail": "Invalid token: Signature verification failed"
}
```

**처리 방법**: 
1. Refresh Token으로 새 Access Token 요청
2. 실패 시 로그인 페이지로 리다이렉트

#### 403 Forbidden (GraphQL)

GraphQL에서 인증 없이 보호된 쿼리 실행 시:

```json
{
  "data": null,
  "errors": [
    {
      "message": "인증이 필요합니다. Authorization 헤더에 Bearer 토큰을 제공해주세요."
    }
  ]
}
```

### 토큰 갱신 (프론트엔드 책임)

Access Token 갱신은 **프론트엔드에서 OIDC Provider와 직접** 처리합니다:

```javascript
// 예시: oidc-client-ts 사용
import { UserManager } from 'oidc-client-ts';

const userManager = new UserManager({
  authority: 'https://auth.example.com/realms/myrealm',
  client_id: 'my-frontend-app',
  redirect_uri: 'http://localhost:3000/callback',
});

// 자동 토큰 갱신
userManager.events.addAccessTokenExpiring(async () => {
  try {
    await userManager.signinSilent();
  } catch (error) {
    // 갱신 실패 → 재로그인 필요
    await userManager.signinRedirect();
  }
});
```

---

## 6. OIDC Provider별 설정 예시

### Keycloak

```bash
# Keycloak 설정
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://keycloak.example.com/realms/myrealm
OIDC_AUDIENCE=my-frontend-app
```

**Keycloak 설정 시 확인 사항:**
- Client 생성 시 `Access Type`: `public` (SPA) 또는 `confidential`
- `Valid Redirect URIs`: 프론트엔드 URL 등록
- `Web Origins`: CORS 설정을 위한 프론트엔드 origin

**프론트엔드 설정:**
```javascript
const oidcConfig = {
  authority: 'https://keycloak.example.com/realms/myrealm',
  client_id: 'my-frontend-app',
  redirect_uri: 'http://localhost:3000/callback',
  scope: 'openid profile email',
};
```

### Google

```bash
# Google 설정
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://accounts.google.com
OIDC_AUDIENCE=your-google-client-id.apps.googleusercontent.com
```

**Google Cloud Console 설정:**
1. OAuth 2.0 클라이언트 ID 생성
2. 승인된 JavaScript 원본에 프론트엔드 URL 추가
3. 승인된 리다이렉션 URI 추가

**프론트엔드 설정:**
```javascript
const oidcConfig = {
  authority: 'https://accounts.google.com',
  client_id: 'your-google-client-id.apps.googleusercontent.com',
  redirect_uri: 'http://localhost:3000/callback',
  scope: 'openid profile email',
};
```

### Auth0

```bash
# Auth0 설정
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://your-tenant.auth0.com/
OIDC_AUDIENCE=https://your-api-identifier
```

!!! warning "주의"
    Auth0의 Issuer URL은 끝에 `/`가 포함되어야 합니다.

**Auth0 Dashboard 설정:**
1. Application 생성 (Single Page Application)
2. API 생성 및 Identifier 설정
3. Allowed Callback URLs, Logout URLs, Web Origins 설정

**프론트엔드 설정:**
```javascript
const oidcConfig = {
  authority: 'https://your-tenant.auth0.com',
  client_id: 'your-auth0-client-id',
  redirect_uri: 'http://localhost:3000/callback',
  scope: 'openid profile email',
  audience: 'https://your-api-identifier',
};
```

---

## 관련 코드 참조

| 파일 | 설명 |
|------|------|
| `app/core/auth.py` | OIDC 인증 핵심 로직 |
| `app/core/config.py` | 환경변수 설정 |
| `app/api/v1/graphql.py` | GraphQL 컨텍스트 인증 처리 |

### CurrentUser 모델

```python
class CurrentUser(BaseModel):
    sub: str          # 사용자 고유 식별자 (owner_id로 사용)
    email: str | None
    name: str | None
    raw_claims: dict  # 전체 JWT 클레임 (필요시 확장용)
```

### FastAPI Dependency 사용법

```python
from app.core.auth import CurrentUser, get_current_user

@router.get("/protected")
async def protected_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
):
    return {"user_id": current_user.sub}
```

---

## FAQ

### Q: 인증 없이 빠르게 테스트하고 싶어요

`.env` 파일에 `OIDC_ENABLED=false` 추가 후 서버 재시작

### Q: 다른 사용자의 데이터가 보이지 않아요

정상입니다. 모든 데이터는 `owner_id`로 격리되어 있습니다.

### Q: 토큰 만료 시간은 어떻게 되나요?

OIDC Provider 설정에 따라 다릅니다. 일반적으로:
- Access Token: 5분 ~ 1시간
- Refresh Token: 1일 ~ 30일

### Q: JWKS 캐시가 갱신되지 않아요

서버 재시작 또는 캐시 TTL(기본 1시간) 만료를 기다리세요.
