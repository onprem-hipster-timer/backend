    # Rate Limit 가이드

이 문서는 백엔드 API의 Rate Limit(요청 제한) 시스템에 대한 가이드입니다.

## 1. Rate Limit 개요

Rate Limit은 API 남용을 방지하고 서버 안정성을 보장하기 위한 요청 제한 시스템입니다.

### 동작 방식

```mermaid
sequenceDiagram
    participant Client
    participant Middleware as RateLimitMiddleware
    participant Storage as InMemoryStorage
    participant API as API Endpoint

    Client->>Middleware: API 요청
    Middleware->>Middleware: 규칙 매칭 (method + path)
    Middleware->>Storage: 요청 카운트 조회
    alt 한도 초과
        Storage-->>Middleware: 초과 상태
        Middleware-->>Client: 429 Too Many Requests
    else 한도 이내
        Storage-->>Middleware: 허용 상태
        Middleware->>API: 요청 전달
        API-->>Middleware: 응답
        Middleware-->>Client: 응답 + X-RateLimit-* 헤더
    end
```

### 핵심 개념

| 용어 | 설명 |
|------|------|
| **Window** | 요청 카운트를 측정하는 시간 윈도우 (기본 60초) |
| **Max Requests** | 윈도우 내 허용되는 최대 요청 수 |
| **User Identifier** | 사용자 식별 방법 (JWT sub 또는 IP 주소) |
| **Sliding Window** | 슬라이딩 윈도우 방식으로 정확한 요청 제한 |

### 사용자 식별

Rate Limit은 사용자별로 독립적으로 적용됩니다:

| 인증 상태 | 식별자 |
|-----------|--------|
| 인증됨 | JWT의 `sub` claim (OIDC 사용자 ID) |
| 미인증 | 클라이언트 IP 주소 (`X-Forwarded-For` 또는 직접 연결 IP) |

---

## 2. 환경변수 설정

### 환경변수 목록

| 환경변수 | 필수 | 기본값 | 설명 |
|----------|------|--------|------|
| `RATE_LIMIT_ENABLED` | X | `true` | Rate Limit 활성화 여부 |
| `RATE_LIMIT_DEFAULT_WINDOW` | X | `60` | 기본 윈도우 크기 (초) |
| `RATE_LIMIT_DEFAULT_REQUESTS` | X | `60` | 기본 최대 요청 수 |
| `CF_ENABLED` | X | `false` | Cloudflare 프록시 사용 여부 |
| `CF_IP_CACHE_TTL` | X | `86400` | Cloudflare IP 목록 캐시 TTL (초, 기본 24시간) |
| `TRUSTED_PROXY_IPS` | X | `""` | 신뢰할 프록시 IP 목록 (콤마 구분, CIDR 지원) |

### 예시 설정 (.env)

```bash
# Rate Limit 설정
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_WINDOW=60
RATE_LIMIT_DEFAULT_REQUESTS=60
```

### Docker Compose 설정

```yaml
# compose.yaml
services:
  backend:
    environment:
      - RATE_LIMIT_ENABLED=true
      - RATE_LIMIT_DEFAULT_WINDOW=60
      - RATE_LIMIT_DEFAULT_REQUESTS=60
```

---

## 3. 활성화/비활성화

### Rate Limit 비활성화

개발 환경이나 테스트 시 Rate Limit을 비활성화할 수 있습니다.

#### 방법 1: 환경변수 설정

```bash
# .env 파일
RATE_LIMIT_ENABLED=false
```

#### 방법 2: 환경변수 직접 지정

```bash
# Linux/Mac
RATE_LIMIT_ENABLED=false uvicorn app.main:app --reload

# Windows (PowerShell)
$env:RATE_LIMIT_ENABLED="false"; uvicorn app.main:app --reload
```

### 비활성화 시 동작

- 모든 요청이 제한 없이 통과됩니다
- X-RateLimit-* 응답 헤더가 추가되지 않습니다
- 로그에 Rate Limit 관련 메시지가 출력되지 않습니다

> **주의**: 프로덕션 환경에서는 반드시 `RATE_LIMIT_ENABLED=true`로 설정하세요!

---

## 4. 프록시 환경 설정

프록시(Cloudflare, Nginx, 로드밸런서 등) 뒤에서 운영할 때 클라이언트 IP를 정확히 식별하기 위한 설정입니다.

### 보안 경고

> **⚠️ 중요**: 프록시 헤더(`X-Forwarded-For`, `CF-Connecting-IP`)는 클라이언트가 조작할 수 있습니다.  
> 반드시 신뢰할 수 있는 프록시에서 온 요청에서만 이 헤더를 사용해야 합니다.

### Cloudflare 환경 (권장)

Cloudflare를 사용하는 경우 `CF_ENABLED=true`로 설정하세요:

```bash
# .env
CF_ENABLED=true
CF_IP_CACHE_TTL=86400  # 24시간 (cf 권장)
```

#### IP 목록 캐시

- Cloudflare IP 목록은 거의 변경되지 않습니다 (보통 몇 달에 1번)
- 기본 캐시 TTL: 24시간 (`CF_IP_CACHE_TTL=86400`)
- 앱 재시작 또는 TTL 만료 시 백그라운드에서 자동 갱신

#### Fetch 실패 시 동작

1. **이전 캐시 있음**: 이전 캐시 계속 사용
2. **캐시 없음**: Fail-Safe 모드 - 프록시 헤더 무시, `request.client.host` 직접 사용

### Nginx/기타 프록시 환경

Cloudflare가 아닌 다른 프록시를 사용하는 경우 `TRUSTED_PROXY_IPS`를 설정하세요:

```bash
# .env
CF_ENABLED=false  # 기본값
TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

#### 지원 형식

- 단일 IP: `127.0.0.1`
- CIDR 범위: `10.0.0.0/8`
- 콤마로 구분: `127.0.0.1,10.0.0.0/8`\

### 직접 연결 (개발 환경)

프록시 없이 직접 연결하는 경우 아무 설정도 필요 없습니다:

```bash
# .env
CF_ENABLED=false       # 기본값
TRUSTED_PROXY_IPS=     # 기본값 (빈 문자열)
```

모든 프록시 헤더를 무시하고 `request.client.host`를 직접 사용합니다.

### 설정 매트릭스

| CF_ENABLED | TRUSTED_PROXY_IPS | 요청 출처 | IP 추출 방식 |
|------------|-------------------|----------|-------------|
| `true` | (무시됨) | Cloudflare IP | `CF-Connecting-IP` 헤더 |
| `true` | (무시됨) | 다른 IP | `request.client.host` |
| `false` | 설정됨 | Trusted IP | `X-Forwarded-For` 헤더 |
| `false` | 설정됨 | 다른 IP | `request.client.host` |
| `false` | 비어있음 | 어디든 | `request.client.host` |

### Docker Compose 설정 예시

```yaml
# compose.yaml
services:
  backend:
    environment:
      # Cloudflare 환경
      - CF_ENABLED=true
      
      # 또는 Nginx 프록시 환경
      # - CF_ENABLED=false
      # - TRUSTED_PROXY_IPS=nginx,10.0.0.0/8
```

---

## 5. 엔드포인트별 규칙

Rate Limit 규칙은 엔드포인트와 HTTP 메서드에 따라 다르게 적용됩니다.

### 기본 규칙

| 엔드포인트 패턴 | 메서드 | Window | Max Requests | 설명 |
|-----------------|--------|--------|--------------|------|
| `/v1/todos` | POST | 60초 | 30 | Todo 생성 제한 |
| `/v1/schedules` | POST | 60초 | 30 | Schedule 생성 제한 |
| `/v1/timers` | POST | 60초 | 30 | Timer 생성 제한 |
| `/v1/tags` | POST | 60초 | 30 | Tag 생성 제한 |
| `/v1/tags/groups` | POST | 60초 | 30 | TagGroup 생성 제한 |
| `/v1/todos/*` | ALL | 60초 | 100 | Todo 일반 작업 |
| `/v1/schedules/*` | ALL | 60초 | 60 | Schedule 일반 작업 |
| `/v1/timers/*` | ALL | 60초 | 60 | Timer 일반 작업 |
| `/v1/tags/*` | ALL | 60초 | 60 | Tag 일반 작업 |
| `/v1/graphql` | ALL | 60초 | 60 | GraphQL 요청 |
| `/v1/*` | ALL | 60초 | 60 | 기타 API (폴백) |

### 규칙 적용 우선순위

1. **구체적인 규칙 우선**: 더 구체적인 경로/메서드 규칙이 먼저 적용됩니다
2. **첫 번째 매칭 사용**: 규칙 리스트를 순회하며 첫 번째 매칭 규칙 사용
3. **폴백 규칙**: 매칭되는 규칙이 없으면 `/v1/*` 전역 규칙 적용

### 예시: POST /v1/todos

```
요청: POST /v1/todos
→ 규칙 매칭: RateLimitRule(methods=["POST"], path_pattern="/v1/todos", ...)
→ 적용: 60초당 30회 제한
```

### 예시: GET /v1/todos

```
요청: GET /v1/todos
→ POST 전용 규칙 스킵
→ 규칙 매칭: RateLimitRule(path_pattern="/v1/todos", ...)
→ 적용: 60초당 100회 제한
```

---

## 6. 응답 헤더

모든 `/v1/*` API 응답에 Rate Limit 정보 헤더가 포함됩니다.

### 헤더 목록

| 헤더 | 설명 | 예시 |
|------|------|------|
| `X-RateLimit-Limit` | 윈도우 내 최대 허용 요청 수 | `60` |
| `X-RateLimit-Remaining` | 남은 요청 수 | `42` |
| `X-RateLimit-Reset` | 윈도우 리셋까지 남은 시간 (초) | `35` |

### 응답 예시

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 35
Content-Type: application/json

{"id": "...", "title": "My Schedule"}
```

### 429 응답 시 추가 헤더

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 35
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 35
Content-Type: application/json

{
  "detail": "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
  "retry_after": 35
}
```

---

## 7. 429 에러 처리

### 프론트엔드 처리 방법

#### JavaScript (fetch)

```javascript
const response = await fetch('http://localhost:2614/v1/schedules', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(data),
});

if (response.status === 429) {
  const errorData = await response.json();
  const retryAfter = response.headers.get('Retry-After') || errorData.retry_after;
  
  // 사용자에게 알림
  showNotification(`요청 한도 초과. ${retryAfter}초 후 다시 시도해주세요.`);
  
  // 자동 재시도 (선택적)
  setTimeout(() => {
    retryRequest();
  }, retryAfter * 1000);
}
```

#### Axios 인터셉터

```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:2614/v1',
});

// 응답 인터셉터: 429 처리
api.interceptors.response.use(
  (response) => {
    // 남은 요청 수 로깅 (디버깅용)
    const remaining = response.headers['x-ratelimit-remaining'];
    if (remaining && parseInt(remaining) < 10) {
      console.warn(`Rate limit warning: ${remaining} requests remaining`);
    }
    return response;
  },
  async (error) => {
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers['retry-after'] || 60;
      
      // 토스트 알림
      showToast(`요청 한도 초과. ${retryAfter}초 후 다시 시도해주세요.`, 'warning');
      
      // 자동 재시도 (지수 백오프)
      await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
      return api.request(error.config);
    }
    return Promise.reject(error);
  }
);
```

### 권장 클라이언트 동작

1. **Retry-After 헤더 존중**: 서버가 제공하는 대기 시간을 따르세요
2. **지수 백오프**: 연속 429 응답 시 대기 시간을 점진적으로 증가
3. **사용자 피드백**: 명확한 에러 메시지와 남은 시간 표시
4. **요청 배치**: 가능하면 여러 요청을 하나로 묶기 (GraphQL 활용)

---

## 8. 규칙 커스터마이징

### 규칙 수정 위치

```
app/ratelimit/config.py
```

### 규칙 추가 예시

```python
# app/ratelimit/config.py

RATE_LIMIT_RULES: List[RateLimitRule] = [
    # 새로운 규칙 추가 (기존 규칙보다 위에 배치)
    RateLimitRule(
        methods=["POST"],
        path_pattern="/v1/bulk-import",  # 대량 가져오기 엔드포인트
        window_seconds=3600,              # 1시간
        max_requests=5,                   # 시간당 5회만 허용
    ),
    
    # ... 기존 규칙들 ...
]
```

### 규칙 구조

```python
class RateLimitRule(BaseModel):
    methods: Optional[List[str]] = None  # None = 모든 메서드
    path_pattern: str                     # fnmatch 패턴
    window_seconds: int                   # 윈도우 크기 (초)
    max_requests: int                     # 최대 요청 수
```

### Path Pattern 문법

`fnmatch` 패턴을 사용합니다:

| 패턴 | 설명 | 매칭 예시 |
|------|------|-----------|
| `/v1/todos` | 정확히 일치 | `/v1/todos` |
| `/v1/todos/*` | 하위 경로 포함 | `/v1/todos/123`, `/v1/todos/123/complete` |
| `/v1/*/export` | 중간 와일드카드 | `/v1/schedules/export`, `/v1/todos/export` |

---

## 9. WebSocket Rate Limit

WebSocket 연결에 대한 레이트 리밋은 REST API와 별도로 관리됩니다.

### 동작 방식

```mermaid
sequenceDiagram
    participant Client
    participant WS as WebSocket Handler
    participant Limiter as WSRateLimiter
    participant Storage as InMemoryStorage

    Note over Client,WS: 연결 시도
    Client->>WS: WebSocket 연결 요청
    WS->>Limiter: 연결 Rate Limit 체크
    Limiter->>Storage: 연결 카운트 조회
    alt 연결 한도 초과
        Storage-->>Limiter: 초과 상태
        Limiter-->>WS: 차단
        WS-->>Client: 연결 거부 (4029)
    else 연결 허용
        Storage-->>Limiter: 허용
        WS-->>Client: 연결 수락

        Note over Client,WS: 메시지 교환
        Client->>WS: 메시지 전송
        WS->>Limiter: 메시지 Rate Limit 체크
        alt 메시지 한도 초과
            Limiter-->>WS: 차단
            WS-->>Client: 에러 메시지 (RATE_LIMIT_EXCEEDED)
        else 메시지 허용
            WS->>WS: 메시지 처리
            WS-->>Client: 응답 메시지
        end
    end
```

### 환경변수 설정

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `WS_RATE_LIMIT_ENABLED` | `true` | WebSocket Rate Limit 활성화 |
| `WS_CONNECT_WINDOW` | `60` | 연결 제한 윈도우 (초) |
| `WS_CONNECT_MAX` | `10` | 윈도우 내 최대 연결 횟수 |
| `WS_MESSAGE_WINDOW` | `60` | 메시지 제한 윈도우 (초) |
| `WS_MESSAGE_MAX` | `120` | 윈도우 내 최대 메시지 수 |

### 예시 설정 (.env)

```bash
# WebSocket Rate Limit 설정
WS_RATE_LIMIT_ENABLED=true
WS_CONNECT_WINDOW=60      # 1분
WS_CONNECT_MAX=10         # 분당 10회 연결
WS_MESSAGE_WINDOW=60      # 1분
WS_MESSAGE_MAX=120        # 분당 120개 메시지
```

### 두 가지 제한 유형

#### 1. 연결 제한 (Connection Rate Limit)

- **목적**: 동일 사용자가 짧은 시간 내에 반복적으로 연결/해제하는 것 방지
- **적용 시점**: WebSocket 연결 수락 전
- **초과 시**: 연결 거부 (close code: `4029`)

```javascript
// 클라이언트 측 에러 처리
ws.onclose = (event) => {
  if (event.code === 4029) {
    console.error('연결 Rate Limit 초과:', event.reason);
    // 재연결 대기
  }
};
```

#### 2. 메시지 제한 (Message Rate Limit)

- **목적**: 연결된 사용자의 메시지 폭주 방지
- **적용 시점**: 각 메시지 수신 시
- **초과 시**: 에러 메시지 응답 (연결 유지)

```json
{
  "type": "error",
  "payload": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "WebSocket 메시지 한도를 초과했습니다. 35초 후에 다시 시도해주세요."
  }
}
```

### 프론트엔드 처리

```javascript
// WebSocket Rate Limit 처리 예시
class TimerWebSocket {
  constructor(url, token) {
    this.url = url;
    this.token = token;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.connect();
  }

  connect() {
    // 보안상 쿼리 파라미터 대신 Sec-WebSocket-Protocol 헤더 사용
    this.ws = new WebSocket(this.url, [`authorization.bearer.${this.token}`]);

    this.ws.onclose = (event) => {
      if (event.code === 4029) {
        // 연결 Rate Limit - 지수 백오프 재연결
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 60000);
        console.warn(`연결 Rate Limit. ${delay/1000}초 후 재연결...`);
        setTimeout(() => this.connect(), delay);
        this.reconnectAttempts++;
      }
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'error' && message.payload.code === 'RATE_LIMIT_EXCEEDED') {
        // 메시지 Rate Limit - 일시적으로 전송 중지
        console.warn('메시지 Rate Limit:', message.payload.message);
        this.pauseMessageQueue();
      }
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0; // 성공 시 리셋
    };
  }

  pauseMessageQueue() {
    // 메시지 큐 일시 중지 로직
  }
}
```

### 권장 클라이언트 동작

| 상황 | 권장 동작 |
|------|-----------|
| 연결 Rate Limit (4029) | 지수 백오프로 재연결 시도 |
| 메시지 Rate Limit | 메시지 큐 일시 중지, 에러 메시지에서 retry_after 확인 |
| 정상 연결 끊김 | 즉시 재연결 시도 |

### 비활성화

개발/테스트 환경에서 WebSocket Rate Limit을 비활성화할 수 있습니다:

```bash
WS_RATE_LIMIT_ENABLED=false
```

> **주의**: 프로덕션 환경에서는 반드시 활성화하세요!

---

## 관련 코드 참조

| 파일 | 설명 |
|------|------|
| `app/ratelimit/config.py` | 규칙 정의 및 매칭 로직 |
| `app/ratelimit/middleware.py` | REST API Rate Limit 미들웨어 |
| `app/ratelimit/limiter.py` | 요청 카운트 및 제한 로직 |
| `app/ratelimit/websocket.py` | WebSocket Rate Limit 로직 |
| `app/ratelimit/cloudflare.py` | Cloudflare/Trusted Proxy IP 관리 및 클라이언트 IP 추출 |
| `app/ratelimit/storage/memory.py` | 인메모리 저장소 (슬라이딩 윈도우) |
| `app/websocket/router.py` | WebSocket 엔드포인트 (Rate Limit 적용) |
| `app/core/config.py` | 환경변수 설정 |

---

## FAQ

### Q: Rate Limit을 테스트하고 싶어요

테스트 환경에서 빠르게 한도에 도달하도록 설정할 수 있습니다:

```bash
# 테스트용 설정
RATE_LIMIT_DEFAULT_WINDOW=10
RATE_LIMIT_DEFAULT_REQUESTS=5
```

또는 비활성화 후 테스트:

```bash
RATE_LIMIT_ENABLED=false
```

### Q: 특정 IP나 사용자를 화이트리스트에 추가하고 싶어요

현재 버전에서는 화이트리스트 기능이 없습니다. 필요시 `RateLimitMiddleware`를 수정하세요:

```python
# app/ratelimit/middleware.py

WHITELIST_IPS = {"192.168.1.100", "10.0.0.1"}

async def dispatch(self, request, call_next):
    # 화이트리스트 IP는 스킵
    client_ip = request.client.host if request.client else None
    if client_ip in WHITELIST_IPS:
        return await call_next(request)
    # ... 기존 로직 ...
```

### Q: Redis를 사용하고 싶어요

현재는 인메모리 저장소만 지원합니다. Redis 지원이 필요하면 `app/ratelimit/storage/` 디렉토리에 새 저장소를 구현하세요:

```python
# app/ratelimit/storage/redis.py
from app.ratelimit.storage.base import RateLimitStorage

class RedisStorage(RateLimitStorage):
    async def record_request(self, key: str, window_seconds: int) -> int:
        # Redis 구현
        pass
    
    async def get_window_info(self, key: str, window_seconds: int) -> tuple[int, int]:
        # Redis 구현
        pass
```

### Q: GraphQL 요청도 Rate Limit이 적용되나요?

네, `/v1/graphql` 엔드포인트에 60초당 60회 제한이 적용됩니다. 
GraphQL의 특성상 하나의 요청으로 여러 쿼리를 묶을 수 있으므로 효율적으로 사용하세요.

### Q: 분산 환경에서는 어떻게 되나요?

현재 인메모리 저장소는 단일 인스턴스용입니다. 분산 환경에서는:
1. Redis 저장소 구현 필요
2. 또는 로드밸런서에서 Rate Limit 처리 (nginx, Kong 등)
