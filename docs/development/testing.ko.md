# pytest로 테스트 실행하기

이 문서는 프로젝트 루트의 `tests/` 폴더를 이용해 **pytest**로 테스트를 실행하는 방법을 소개합니다.

## 사전 요구사항

- Python 3.11 이상
- 개발 의존성 설치: `pip install -r requirements-dev.txt`

---

## 기본 명령어

### 전체 테스트 실행

```bash
pytest
```

- 기본: 상세 출력, 짧은 traceback, 첫 실패 시 중단
- `tests/` 아래 모든 테스트 수집·실행

### 출력 옵션

```bash
# 상세 출력 (-v)
pytest -v

# 짧은 traceback (기본 권장)
pytest --tb=short

# 첫 실패 시 중단
pytest -x

# 조합 예시
pytest -v --tb=short -x
```

### 커버리지

```bash
# app 패키지 커버리지 + 터미널 요약
pytest --cov=app --cov-report=term-missing

# HTML 리포트 생성 (브라우저에서 확인)
pytest --cov=app --cov-report=html
```

---

## 디렉터리/파일 지정

`tests/` 폴더 구조에 맞춰 특정 영역만 실행할 수 있습니다.

### 특정 디렉터리

```bash
# 도메인 스케줄 테스트만
pytest tests/domain/schedule/

# 도메인 todo 테스트만
pytest tests/domain/todo/

# core (인증 등) 테스트만
pytest tests/core/

# ratelimit 테스트만
pytest tests/ratelimit/
```

### 특정 파일

```bash
pytest tests/test_schedules_e2e.py
pytest tests/domain/schedule/test_service.py
```

### 특정 함수/클래스

```bash
# 테스트 함수 이름으로 (부분 일치)
pytest tests/domain/schedule/ -k "test_create"

# 정확한 테스트 경로
pytest tests/domain/schedule/test_service.py::test_create_schedule
```

---

## 마커로 필터링

`pytest.ini`에 등록된 마커를 사용해 테스트 유형별로 실행할 수 있습니다.

| 마커 | 설명 | 해당 파일 예시 |
|------|------|----------------|
| `e2e` | End-to-end (전체 HTTP API 흐름) | `test_*_e2e.py` |
| `integration` | 통합 테스트 (DB, 트랜잭션 등) | `test_*_integration.py` |
| `ratelimit` | Rate limit 관련 테스트 | `tests/ratelimit/` |

### E2E만 실행

```bash
pytest -m e2e
```

### 통합 테스트만 실행

```bash
pytest -m integration
```

### 특정 마커 제외

```bash
# e2e 제외 (단위·통합만)
pytest -m "not e2e"

# ratelimit 제외
pytest -m "not ratelimit"
```

---

## tests/ 폴더 구조

| 경로 | 설명 |
|------|------|
| `tests/domain/` | 도메인 로직 단위 테스트 (schedule, timer, todo, tag, holiday 등) |
| `tests/core/` | 인증, 설정 등 코어 테스트 |
| `tests/ratelimit/` | Rate limit 미들웨어·스토리지 테스트 |
| `tests/test_*_e2e.py` | REST/GraphQL/WebSocket E2E 테스트 |
| `tests/test_*_integration.py` | DB 연동 통합 테스트 |
| `tests/conftest.py` | 공통 fixture (DB 엔진, 세션, 테스트 유저 등) |

---

## PostgreSQL로 테스트

기본은 SQLite 메모리 DB입니다. PostgreSQL로 실행하려면:

```bash
# 1. PostgreSQL 컨테이너 기동
docker compose -f docker-compose.test.yaml up -d

# 2. 환경 변수 설정 후 pytest
# Windows PowerShell
$env:TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"
pytest

# Linux/macOS
TEST_DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb" pytest

# 3. 정리
docker compose -f docker-compose.test.yaml down -v
```

### PostgreSQL에서만 도는 테스트

SQLite에서는 건너뛰고 `TEST_DATABASE_URL`이 PostgreSQL일 때만 도는 테스트가 있습니다. 동시 요청의 결과를 DB 제약으로 확인하는 테스트입니다.

| 테스트 | 확인하는 것 |
|--------|-------------|
| `tests/domain/guest/test_name_concurrency.py` | 같은 이름의 게스트를 동시에 만들어도 하나만 남는다. 연결 풀이 작아도 동시 생성·이름 변경이 끝나고 다른 요청이 응답한다 |
| `tests/domain/schedule/test_projection_concurrency.py` | 일정과 할 일의 동시 변경 |
| `tests/domain/consent/test_record_concurrency.py` | 같은 약관 버전의 동의 기록이 겹쳐도 처음 동의한 행이 남고, 사용성 분석 동의(`analytics`)는 마지막으로 보낸 값이 남는다 |

## 게스트 계정을 실제 Kratos로 확인

`tests/domain/guest/`는 가짜 Kratos(`tests/domain/guest/fakes.py`)로 돕니다. Kratos 설정 파일(`dev/kratos/kratos.guest.yml`, 훅 본문, 클레임 매퍼)이 backend와 맞는지는 `tests/domain/guest/test_kratos_config.py`가 파일을 읽어 확인합니다. 실제 Kratos로 생성 → 로그인 → JWT → 이름 변경 → 폐기를 확인하는 방법은 [게스트 계정 설정 (Kratos)](../deployment/kratos-guest.ko.md)의 "설정 후 확인"과 "로컬에서 켜기"에 있습니다.

---

## 관련 문서

- [Python 버전 호환성 테스트](python-version-testing.ko.md) — Docker로 여러 Python 버전에서 테스트하는 방법
