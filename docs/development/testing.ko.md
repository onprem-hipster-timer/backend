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

---

## 관련 문서

- [Python 버전 호환성 테스트](python-version-testing.ko.md) — Docker로 여러 Python 버전에서 테스트하는 방법
