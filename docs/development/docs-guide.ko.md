# 문서 작성 및 번역 가이드

이 문서는 프로젝트 문서를 작성·수정하거나, 새 언어 번역을 추가하려는 기여자를 위한 가이드입니다.

---

## 문서 구조

### 폴더 레이아웃

```
docs/
├── index.ko.md              # 홈 (한국어)
├── index.en.md              # 홈 (영어)
├── getting-started/
│   ├── installation.ko.md
│   ├── installation.en.md
│   └── ...
├── api/
├── guides/
├── deployment/
└── development/
```

### 파일 명명 규칙

| 로케일 | 접미사 | 예시 |
|--------|--------|------|
| 한국어 (기본) | `.ko.md` | `installation.ko.md` |
| 영어 | `.en.md` | `installation.en.md` |
| 일본어 (추가 시) | `.ja.md` | `installation.ja.md` |

- **기본 언어는 한국어(`ko`)**입니다.
- 영어(`.en.md`)가 없으면 해당 페이지는 한국어 문서가 영어 경로에서도 표시됩니다 (`fallback_to_default: true`).

### 번역 기준

!!! important "기준 언어"
    **번역에 문제가 있을 경우 한국어 자료를 메인(기준)으로 삼습니다.**  
    In case of discrepancies in translation, the **Korean version is the authoritative source.**

---

## 새 문서 작성하기

### 1. 파일 생성

적절한 폴더에 `파일명.ko.md`를 만듭니다.

```markdown
# 페이지 제목

본문 내용...
```

### 2. nav에 추가

`mkdocs.yml`의 `nav` 섹션에 항목을 추가합니다.  
**로케일 접미사 없이** 파일명만 씁니다 (i18n 플러그인이 자동 매핑).

```yaml
nav:
  - Development:
    - Rate Limiting: development/rate-limit.md      # .ko.md / .en.md 자동 매핑
    - Testing: development/testing.md
    - 새 문서: development/new-doc.md               # 추가
```

### 3. 영어 버전 (선택)

영어 문서를 제공하려면 같은 경로에 `.en.md` 파일을 만듭니다.

```
docs/development/new-doc.ko.md   ← 한국어
docs/development/new-doc.en.md   ← 영어 (선택)
```

영어 파일이 없으면 `/en/...` 경로에서도 한국어 문서가 보입니다.

---

## 마크다운 기능

이 프로젝트는 MkDocs Material 테마와 여러 확장을 사용합니다.

### 코드 블록

````markdown
```python
def hello():
    print("Hello, World!")
```
````

- 줄 번호 자동 (`anchor_linenums`)
- 복사 버튼 (`content.code.copy`)

### Admonition (콜아웃)

```markdown
!!! note "참고"
    중요한 정보를 강조할 때 사용합니다.

!!! warning "주의"
    주의가 필요한 내용입니다.

!!! tip "팁"
    유용한 팁입니다.
```

**결과:**

!!! note "참고"
    중요한 정보를 강조할 때 사용합니다.

### 접을 수 있는 블록

```markdown
??? info "클릭해서 펼치기"
    숨겨진 내용입니다.
```

### 탭

```markdown
=== "Python"
    ```python
    print("Hello")
    ```

=== "JavaScript"
    ```javascript
    console.log("Hello");
    ```
```

### Mermaid 다이어그램

````markdown
```mermaid
flowchart LR
    A[시작] --> B[처리]
    B --> C[끝]
```
````

### 표

```markdown
| 열1 | 열2 | 열3 |
|-----|-----|-----|
| 값1 | 값2 | 값3 |
```

---

## 새 언어 추가하기

프로젝트에 새 언어(예: 일본어)를 추가하려면:

### 1. mkdocs.yml 수정

`plugins` → `i18n` → `languages`에 새 로케일을 추가합니다.

```yaml
plugins:
  - i18n:
      docs_structure: suffix
      fallback_to_default: true
      languages:
        - locale: ko
          name: 한국어
          default: true
          build: true
        - locale: en
          name: English
          build: true
        - locale: ja              # 추가
          name: 日本語
          build: true
```

### 2. 번역 파일 생성

번역할 페이지마다 `.ja.md` 파일을 만듭니다.

```
docs/index.ja.md
docs/getting-started/installation.ja.md
...
```

### 3. Fallback 동작

- 일본어 파일이 없는 페이지는 **기본 언어(ko) 문서**가 `/ja/...` 경로에서 표시됩니다.
- 전체 번역이 완료되지 않아도 사이트는 정상 빌드됩니다.

### 4. 테마 언어 (선택)

MkDocs Material 테마 UI도 해당 언어로 보이게 하려면, 테마가 그 언어를 지원하는지 확인하세요.  
지원 언어 목록: [MkDocs Material Localization](https://squidfunk.github.io/mkdocs-material/setup/changing-the-language/)

---

## 로컬에서 문서 확인

```bash
# 의존성 설치 (최초 1회)
pip install mkdocs mkdocs-material mkdocs-static-i18n mkdocs-include-markdown-plugin mkdocs-render-swagger-plugin

# 개발 서버 실행
mkdocs serve

# 브라우저에서 확인
# http://127.0.0.1:8000
```

### 언어별 확인

- 한국어: `http://127.0.0.1:8000/`
- 영어: `http://127.0.0.1:8000/en/`

---

## 스타일 가이드

### 제목

- H1(`#`)은 페이지당 1개만 사용 (페이지 제목)
- H2(`##`) 이하로 섹션 구분

### 링크

**같은 언어 내 링크** (권장):

```markdown
자세한 내용은 [인증 가이드](../guides/auth.ko.md)를 참고하세요.
```

**외부 링크**:

```markdown
[MkDocs 공식 문서](https://www.mkdocs.org/)
```

### 이미지

```markdown
![대체 텍스트](../assets/image.png)
```

이미지는 `docs/assets/` 폴더에 저장합니다.

### 용어 일관성

| 영어 | 한국어 |
|------|--------|
| Schedule | 일정 |
| Timer | 타이머 |
| Todo | 투두 |
| Tag | 태그 |
| Authentication | 인증 |
| Rate Limiting | Rate Limiting (그대로) |

---

## 기여 절차

1. 저장소 Fork 또는 브랜치 생성
2. 문서 작성/수정
3. `mkdocs serve`로 로컬 확인
4. Pull Request 생성
5. 리뷰 후 병합

문서 기여를 환영합니다!
