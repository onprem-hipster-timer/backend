# 애플리케이션 빌드 및 실행

준비가 되면 다음 명령어로 애플리케이션을 시작하세요:
`docker compose up --build`.

애플리케이션은 http://localhost:2614 에서 접근 가능합니다.

# 클라우드에 애플리케이션 배포

먼저 이미지를 빌드하세요. 예: `docker build -t myapp .`
클라우드가 개발 머신과 다른 CPU 아키텍처를 사용하는 경우 (예: Mac M1이고 클라우드 제공업체가 amd64인 경우),
해당 플랫폼용으로 이미지를 빌드하세요. 예:
`docker build --platform=linux/amd64 -t myapp .`.

그런 다음 레지스트리에 푸시하세요. 예: `docker push myregistry.com/myapp`.

빌드 및 푸시에 대한 자세한 내용은 Docker의 [시작하기](https://docs.docker.com/go/get-started-sharing/) 문서를 참조하세요.

### 참고 자료
* [Docker Python 가이드](https://docs.docker.com/language/python/)
