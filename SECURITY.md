# Security Policy

**[한국어 버전은 아래에 있습니다](#보안-정책)**

## Reporting a Vulnerability

**Do NOT report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability, please report it privately:

### How to Report

1. **Email**: Send details to jjh4450git@gmail.com
2. **GitHub Security Advisory**: Use the [Security Advisory](https://github.com/onprem-hipster-timer/backend/security/advisories/new) feature (preferred)

### What to Include

- Type of vulnerability (e.g., SQL injection, authentication bypass, XSS)
- Affected component (file path, endpoint, function)
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

| Stage | Timeline |
|-------|----------|
| Initial Response | Within 48 hours |
| Triage & Assessment | Within 1 week |
| Fix Development | Depends on severity |
| Disclosure | After fix is released |

### What to Expect

1. **Acknowledgment**: We'll confirm receipt of your report
2. **Communication**: We'll keep you informed of our progress
3. **Credit**: We'll credit you in the security advisory (unless you prefer anonymity)
4. **No Retaliation**: We will not take legal action against good-faith security researchers

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Previous release | Security fixes only |
| Older versions | No |

## Security Best Practices

When deploying Hipster Timer Backend:

### Production Checklist

- [ ] Set `ENVIRONMENT=production` (disables debug mode and API docs)
- [ ] Configure proper `OIDC_ISSUER_URL` and `OIDC_AUDIENCE`
- [ ] Set strong `ORIGIN_VERIFY_SECRET` if using proxy
- [ ] Configure `CORS_ALLOWED_ORIGINS` explicitly (not `*`)
- [ ] Enable rate limiting (`RATE_LIMIT_ENABLED=true`)
- [ ] Use PostgreSQL with proper credentials
- [ ] Run behind HTTPS-terminating proxy
- [ ] Keep dependencies updated

### Authentication

- Always enable OIDC in production (`OIDC_ENABLED=true`)
- Use short-lived access tokens
- Validate `aud` claim matches your client ID

### Database

- Never expose database port to public internet
- Use strong, unique passwords
- Enable connection encryption (SSL/TLS)

---

# 보안 정책

## 취약점 신고

**보안 취약점을 공개 GitHub 이슈로 신고하지 마세요.**

보안 취약점을 발견하면, 비공개로 신고해 주세요:

### 신고 방법

1. **이메일**: jjh4450git@gmail.com으로 세부 사항 전송
2. **GitHub Security Advisory**: [Security Advisory](https://github.com/onprem-hipster-timer/backend/security/advisories/new) 기능 사용 (권장)

### 포함할 내용

- 취약점 유형 (예: SQL 인젝션, 인증 우회, XSS)
- 영향받는 컴포넌트 (파일 경로, 엔드포인트, 함수)
- 재현 단계
- 잠재적 영향
- 제안하는 수정 방법 (있다면)

### 응답 타임라인

| 단계 | 타임라인 |
|------|----------|
| 초기 응답 | 48시간 이내 |
| 분류 및 평가 | 1주일 이내 |
| 수정 개발 | 심각도에 따라 |
| 공개 | 수정 릴리스 후 |

### 기대할 수 있는 것

1. **확인**: 신고 접수 확인
2. **소통**: 진행 상황 공유
3. **크레딧**: 보안 공지에 기여자로 표시 (익명 희망 시 제외)
4. **보복 없음**: 선의의 보안 연구자에 대해 법적 조치를 취하지 않습니다

## 지원 버전

| 버전 | 지원 |
|------|------|
| 최신 릴리스 | 예 |
| 이전 릴리스 | 보안 수정만 |
| 더 오래된 버전 | 아니오 |

## 보안 모범 사례

Hipster Timer Backend 배포 시:

### 프로덕션 체크리스트

- [ ] `ENVIRONMENT=production` 설정 (디버그 모드 및 API 문서 비활성화)
- [ ] 적절한 `OIDC_ISSUER_URL` 및 `OIDC_AUDIENCE` 설정
- [ ] 프록시 사용 시 강력한 `ORIGIN_VERIFY_SECRET` 설정
- [ ] `CORS_ALLOWED_ORIGINS` 명시적 설정 (`*` 사용 금지)
- [ ] Rate limiting 활성화 (`RATE_LIMIT_ENABLED=true`)
- [ ] 적절한 자격 증명으로 PostgreSQL 사용
- [ ] HTTPS 종료 프록시 뒤에서 실행
- [ ] 의존성 최신 상태 유지

### 인증

- 프로덕션에서 항상 OIDC 활성화 (`OIDC_ENABLED=true`)
- 짧은 수명의 액세스 토큰 사용
- `aud` 클레임이 클라이언트 ID와 일치하는지 검증

### 데이터베이스

- 데이터베이스 포트를 공개 인터넷에 노출하지 않음
- 강력하고 고유한 비밀번호 사용
- 연결 암호화 활성화 (SSL/TLS)

---

*Thank you for helping keep Hipster Timer Backend secure.*
