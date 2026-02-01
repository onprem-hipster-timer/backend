# Hipster Timer Backend 기여 가이드

**[English version](CONTRIBUTING.md)**

Hipster Timer Backend에 관심을 가져주셔서 감사합니다. 이 문서는 기여 절차와 가이드라인을 설명합니다.

## 목차

- [시작하기 전에](#시작하기-전에)
- [개발 환경](#개발-환경)
- [코딩 표준](#코딩-표준)
- [커밋 가이드라인](#커밋-가이드라인)
- [Pull Request 절차](#pull-request-절차)
- [리뷰 프로세스](#리뷰-프로세스)

---

## 시작하기 전에

### 기존 이슈 확인

작업을 시작하기 전에, 동일한 이슈나 PR이 있는지 확인하세요:

1. [기존 이슈](https://github.com/onprem-hipster-timer/backend/issues) 검색
2. [기존 PR](https://github.com/onprem-hipster-timer/backend/pulls) 검색

없다면, 먼저 이슈를 생성하여 변경 사항을 논의하세요.

### Issue First 정책

**사소하지 않은 모든 변경은 먼저 이슈가 필요합니다.**

- 버그 수정: 버그 리포트 이슈 생성
- 새 기능: 기능 요청 이슈 생성
- 문서: 작은 수정은 바로 PR 가능

이를 통해 프로젝트 방향과 일치하는 작업을 보장하고 중복 작업을 방지합니다.

---

## 개발 환경

### 필수 사항

- Python 3.11 이상
- Git
- Docker (선택, PostgreSQL 테스트용)

### 설정

```bash
# Fork 후 clone
git clone https://github.com/YOUR_USERNAME/backend.git
cd backend

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 개발 의존성 설치
pip install -r requirements-dev.txt

# 환경 파일 복사
cp .env.example .env
```

### 테스트 실행

**모든 코드 변경은 테스트를 통과해야 합니다.**

```bash
# 전체 테스트 실행
pytest

# 커버리지 포함
pytest --cov=app --cov-report=term-missing

# 특정 테스트 파일
pytest tests/domain/schedule/test_service.py

# E2E 테스트만
pytest -m e2e
```

### 서버 실행

```bash
uvicorn app.main:app --port 2614 --reload
```

---

## 코딩 표준

### Python 스타일

**PEP 8**을 따르며, 다음 사항을 준수합니다:

- 줄 길이: 최대 120자
- 모든 함수 파라미터와 반환값에 타입 힌트 사용
- 모든 public 함수, 클래스, 모듈에 docstring 작성

### 아키텍처 원칙

1. **계층형 아키텍처**: Router → Service → Domain → Data
2. **도메인 예외**: 서비스에서는 HTTP 예외가 아닌 `DomainException` 하위 클래스 사용
3. **UTC 저장**: 모든 datetime은 UTC naive로 데이터베이스에 저장
4. **소유자 격리**: 모든 리소스는 `owner_id`로 필터링

### 파일 명명

| 유형 | 패턴 | 예시 |
|------|------|------|
| Router | `app/api/v1/{domain}.py` | `schedules.py` |
| Service | `app/domain/{domain}/service.py` | `service.py` |
| Schema | `app/domain/{domain}/schema/dto.py` | `dto.py` |
| Model | `app/models/{domain}.py` | `schedule.py` |
| Test | `tests/domain/{domain}/test_*.py` | `test_service.py` |

---

## 커밋 가이드라인

### 커밋 메시지 형식

Conventional Commit 형식을 따릅니다:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 타입

| 타입 | 설명 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `docs` | 문서만 변경 |
| `style` | 코드 스타일 (포맷팅, 로직 변경 없음) |
| `refactor` | 버그 수정도 기능 추가도 아닌 코드 변경 |
| `test` | 테스트 추가 또는 수정 |
| `chore` | 빌드 프로세스, 의존성 등 |

### 예시

```
feat(schedule): 반복 일정 예외 날짜 처리 추가

반복 일정에서 특정 날짜를 건너뛰거나 수정하는 기능 구현.

- ScheduleException 모델 추가
- expand_recurrence에서 예외 필터링
- 예외 CRUD 엔드포인트 추가

Closes #42
```

### 커밋 원칙

1. **원자적 커밋**: 각 커밋은 하나의 논리적 변경
2. **빌드 가능**: 각 커밋에서 모든 테스트 통과
3. **설명적**: 제목은 무엇을, 본문은 왜를 설명
4. **이슈 참조**: Footer에 `Closes #N` 또는 `Fixes #N` 사용

---

## Pull Request 절차

### 제출 전 체크리스트

- [ ] 모든 테스트 통과 (`pytest`)
- [ ] 스타일 가이드라인 준수
- [ ] 새 코드에 적절한 테스트 작성
- [ ] 필요시 문서 업데이트
- [ ] 커밋 메시지 가이드라인 준수
- [ ] 최신 `main`에 리베이스

### PR 제목 형식

커밋 메시지 제목과 동일:

```
feat(timer): WebSocket 일시정지/재개 지원 추가
fix(auth): JWKS 캐시 만료 처리
docs: Windows 설치 가이드 업데이트
```

### PR 설명

PR 템플릿을 사용하세요. 다음을 포함합니다:

1. **요약**: 이 PR이 하는 일
2. **관련 이슈**: 이슈 링크 (`Closes #N`)
3. **변경 사항**: 변경 내용 목록
4. **테스트 계획**: 검증 방법

### PR 크기

- PR은 집중적이고 적절한 크기로 유지
- 큰 변경은 논리적으로 리뷰 가능한 단위로 분리
- PR이 너무 커지면 분리를 논의

---

## 리뷰 프로세스

### 리뷰어가 확인하는 것

1. **정확성**: 코드가 의도한 대로 동작하는가?
2. **테스트**: 엣지 케이스가 커버되었는가?
3. **아키텍처**: 프로젝트 패턴을 따르는가?
4. **성능**: 명백한 성능 이슈가 있는가?
5. **보안**: 보안 우려 사항이 있는가?

### 리뷰 대응

- 재리뷰 요청 전에 모든 코멘트 처리
- 동의하지 않으면 이유를 설명
- 처리 후 대화를 resolved로 표시

### 리뷰 타임라인

- 메인테이너는 3-5 영업일 내 초기 리뷰 제공 목표
- 복잡한 PR은 더 걸릴 수 있음
- 1주일 후 응답 없으면 PR에서 핑

---

## 도움 받기

- **질문**: [Discussion](https://github.com/onprem-hipster-timer/backend/discussions) 열기
- **버그**: [Issue](https://github.com/onprem-hipster-timer/backend/issues) 생성
- **보안**: [SECURITY.md](SECURITY.md) 참조

---

*좋은 코드는 좋은 리뷰에서 나옵니다. 기여해 주셔서 감사합니다.*
