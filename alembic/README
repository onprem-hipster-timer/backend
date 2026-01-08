# Alembic 마이그레이션 가이드

## 기본 명령어

### 마이그레이션 자동 생성 (모델 변경 감지)
```bash
alembic revision --autogenerate -m "변경 내용 설명"
```

### 마이그레이션 적용
```bash
# 최신 버전으로 업그레이드
alembic upgrade head

# 특정 버전으로 업그레이드
alembic upgrade <revision_id>
```

### 마이그레이션 롤백
```bash
# 한 단계 전으로 롤백
alembic downgrade -1

# 특정 버전으로 롤백
alembic downgrade <revision_id>
```

### 현재 상태 확인
```bash
# 현재 적용된 버전
alembic current

# 마이그레이션 히스토리
alembic history
```

## Best Practices

1. **자동 생성된 마이그레이션 검토**
   - `--autogenerate`는 완벽하지 않음
   - 적용 전 반드시 생성된 스크립트 확인 및 수정

2. **기본값 설정**
   - 기존 데이터가 있는 테이블에 NOT NULL 컬럼 추가 시 `server_default` 필수

3. **마이그레이션 테스트**
   - 프로덕션 적용 전 개발/스테이징 환경에서 테스트

4. **버전 관리**
   - `alembic/versions/` 폴더를 Git에 포함

5. **배포 시 자동 적용**
   - 서버 시작 전 `alembic upgrade head` 실행
