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

## Disclaimer of Liability

### Software Provided "As Is"

This software is licensed under the [Mozilla Public License 2.0 (MPL 2.0)](https://www.mozilla.org/en-US/MPL/2.0/). As stated in the license, the software is provided **"as is"**, without warranty of any kind, either expressed, implied, or statutory. The entire risk as to the quality, performance, and security of the software is with you.

### Modifications and Derivative Works

If you modify, adapt, or create derivative works based on this software in accordance with the MPL 2.0 license terms:

- **You assume full responsibility** for any issues, vulnerabilities, or damages arising from your modifications.
- The original project maintainers and contributors bear **no liability** for defects, security vulnerabilities, or any other problems introduced by your changes.
- You must clearly indicate that you have modified the original software, and you must not misrepresent the origin of the software.

### Hosting and Infrastructure

The project maintainers are **independent from any service provider** that hosts or operates an instance of this software.

- **Infrastructure security** — including but not limited to server configuration, network security, access controls, data backups, and compliance with applicable laws — is the **sole responsibility of the hosting provider / operator**.
- The project maintainers provide no guarantee regarding the security, availability, or reliability of any third-party hosted instance.
- Any data breach, service disruption, or security incident caused by infrastructure misconfiguration or operational negligence is **not the responsibility of the project maintainers**.

### No Professional Advice

Nothing in this software or its documentation constitutes legal, security, or professional advice. Users and operators should consult qualified professionals for their specific deployment and compliance requirements.

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

## 면책 조항

### 소프트웨어 "있는 그대로" 제공

본 소프트웨어는 [Mozilla Public License 2.0 (MPL 2.0)](https://www.mozilla.org/en-US/MPL/2.0/) 하에 라이선스됩니다. 라이선스에 명시된 바와 같이, 소프트웨어는 명시적이든 묵시적이든 어떠한 종류의 보증 없이 **"있는 그대로"** 제공됩니다. 소프트웨어의 품질, 성능 및 보안에 대한 모든 위험은 사용자가 부담합니다.

### 수정 및 파생 저작물

MPL 2.0 라이선스 조건에 따라 본 소프트웨어를 수정, 개조하거나 파생 저작물을 생성하는 경우:

- 수정으로 인해 발생하는 모든 문제, 취약점 또는 손해에 대해 **수정자가 전적으로 책임**을 집니다.
- 원본 프로젝트 관리자 및 기여자는 수정으로 인해 발생하는 결함, 보안 취약점, 기타 문제에 대해 **어떠한 책임도 지지 않습니다**.
- 원본 소프트웨어를 수정했음을 명확히 표시해야 하며, 소프트웨어의 출처를 허위로 표시해서는 안 됩니다.

### 호스팅 및 인프라

프로젝트 관리자는 본 소프트웨어를 호스팅하거나 운영하는 **서비스 제공자와 독립적**입니다.

- 서버 구성, 네트워크 보안, 접근 제어, 데이터 백업, 관련 법규 준수를 포함하되 이에 국한되지 않는 **인프라 보안**은 **호스팅 제공자 / 운영자의 전적인 책임**입니다.
- 프로젝트 관리자는 제3자가 호스팅하는 인스턴스의 보안, 가용성 또는 신뢰성에 대해 어떠한 보증도 하지 않습니다.
- 인프라 설정 오류 또는 운영상 과실로 인한 데이터 유출, 서비스 중단, 보안 사고는 **프로젝트 관리자의 책임이 아닙니다**.

### 전문적 조언 아님

본 소프트웨어 및 관련 문서의 어떤 내용도 법률적, 보안 또는 전문적 조언을 구성하지 않습니다. 사용자 및 운영자는 각자의 배포 및 규정 준수 요건에 대해 전문가와 상담해야 합니다.

---

*Thank you for helping keep Hipster Timer Backend secure.*
