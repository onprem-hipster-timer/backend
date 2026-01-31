# 설치

## 사전 요구사항

- Python 3.11 이상
- pip 또는 uv 패키지 매니저

## 단계별 설치

### 1. 저장소 클론

```bash
git clone https://github.com/onprem-hipster-timer/backend.git
cd backend
```

### 2. 가상 환경 생성

```bash
# 가상 환경 생성
python -m venv .venv

# 가상 환경 활성화
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat

# Linux/macOS
source .venv/bin/activate
```

### 3. 의존성 설치

```bash
# 프로덕션 의존성 설치
pip install -r requirements.txt

# 개발 의존성 설치 (테스트 도구 포함)
pip install -r requirements-dev.txt
```

### 4. 환경 변수 설정

```bash
# 예시 환경 파일 복사
cp .env.example .env

# .env 파일을 설정에 맞게 편집
# 자세한 내용은 구성 가이드 참조
```

### 5. 데이터베이스 초기화

```bash
# 데이터베이스 마이그레이션 실행
alembic upgrade head
```

### 6. 서버 시작

```bash
# 자동 리로드가 있는 개발 서버
uvicorn app.main:app --port 2614 --reload
```

서버는 다음 주소에서 접근 가능합니다:
- REST API: http://localhost:2614/docs (Swagger UI)
- GraphQL: http://localhost:2614/v1/graphql (Apollo Sandbox)

## Docker 설치

### Docker Compose 사용

```bash
# 빌드 및 실행
docker compose up --build

# 백그라운드 실행
docker compose up -d

# 로그 보기
docker compose logs -f
```

### 사전 빌드된 이미지 사용

```bash
# 최신 이미지 받기
docker pull ghcr.io/onprem-hipster-timer/backend:latest

# 컨테이너 실행
docker run -d \
  --name hipster-timer-backend \
  -p 2614:2614 \
  -e DATABASE_URL=sqlite:///./data/schedule.db \
  -e OIDC_ENABLED=false \
  -v hipster-timer-data:/app/data \
  ghcr.io/onprem-hipster-timer/backend:latest
```

## 설치 확인

서버를 시작한 후 설치를 확인하세요:

```bash
# 헬스체크
curl http://localhost:2614/health

# 예상 응답:
# {"status":"healthy","version":"1.0.0","environment":"development"}
```

## 문제 해결

### 일반적인 문제

**포트 사용 중**
```bash
# 다른 포트 사용
uvicorn app.main:app --port 8000 --reload
```

**데이터베이스 연결 오류**
- `.env` 파일의 `DATABASE_URL` 확인
- PostgreSQL 사용 시 데이터베이스 서버 실행 확인
- 데이터베이스 권한 확인

**모듈을 찾을 수 없음**
```bash
# 의존성 재설치
pip install -r requirements-dev.txt
```

**권한 거부 (Linux/macOS)**
```bash
# 스크립트 실행 권한 부여
chmod +x .venv/bin/activate
```
