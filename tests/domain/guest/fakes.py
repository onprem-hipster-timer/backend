"""게스트 테스트용 가짜 Kratos(admin·공개 API)와 가짜 게스트 호스트"""
import uuid
from uuid import UUID

import httpx

from app.domain.guest.host import GuestHostStatus

KRATOS_ADMIN = "http://kratos-admin.test"
KRATOS_PUBLIC = "http://kratos-public.test"


class FakeKratos:
    """identity 생성·조회·삭제와 비밀번호 로그인(API 플로우)을 흉내 낸다

    - down: "admin" 또는 "public"이 들어 있으면 그 API는 연결 오류
    - fail_create / fail_list / fail_get: admin 응답을 500으로
    - login_status: 비밀번호가 맞아도 돌려줄 상태 코드 (None이면 200)
    """

    def __init__(self):
        self.identities: dict[str, dict] = {}
        self.passwords: dict[str, str] = {}
        self.deleted: list[str] = []
        self.logins: list[str] = []
        self.down: set[str] = set()
        self.fail_create = False
        self.fail_list = False
        self.fail_get = False
        self.login_status: int | None = None
        self.list_requests: list[httpx.Request] = []

    # ---- 테스트 준비 ----
    def add_identity(self, schema_id: str, traits: dict, password: str = "", verified: bool = False) -> dict:
        identity_id = str(uuid.uuid4())
        identity = {
            "id": identity_id,
            "schema_id": schema_id,
            "traits": dict(traits),
            "verifiable_addresses": [],
            "created_at": "2026-11-14T00:00:00Z",
        }
        self.identities[identity_id] = identity
        self.passwords[identity_id] = password
        return identity

    def name_of(self, identity_id: str) -> str | None:
        return self.identities[identity_id]["traits"].get("name")

    # ---- admin API ----
    def admin(self, request: httpx.Request) -> httpx.Response:
        if "admin" in self.down:
            raise httpx.ConnectError("admin down", request=request)
        path = request.url.path
        if request.method == "POST" and path == "/admin/identities":
            if self.fail_create:
                return httpx.Response(500)
            import json
            body = json.loads(request.content)
            identity = self.add_identity(
                body["schema_id"], body["traits"], body["credentials"]["password"]["config"]["password"]
            )
            return httpx.Response(201, json=identity)
        if request.method == "GET" and path == "/admin/identities":
            self.list_requests.append(request)
            if self.fail_list:
                return httpx.Response(500)
            ids = request.url.params.get_list("ids")
            return httpx.Response(200, json=[self.identities[i] for i in ids if i in self.identities])
        if path.startswith("/admin/identities/"):
            identity_id = path.rsplit("/", 1)[-1]
            if request.method == "GET":
                if self.fail_get:
                    return httpx.Response(500)
                if identity_id not in self.identities:
                    return httpx.Response(404)
                return httpx.Response(200, json=self.identities[identity_id])
            if request.method == "DELETE":
                if identity_id not in self.identities:
                    return httpx.Response(404)
                del self.identities[identity_id]
                self.deleted.append(identity_id)
                return httpx.Response(204)
        return httpx.Response(404)

    # ---- 공개 API ----
    def public(self, request: httpx.Request) -> httpx.Response:
        if "public" in self.down:
            raise httpx.ConnectError("public down", request=request)
        path = request.url.path
        if request.method == "GET" and path == "/self-service/login/api":
            return httpx.Response(200, json={"id": str(uuid.uuid4())})
        if request.method == "POST" and path == "/self-service/login":
            import json
            body = json.loads(request.content)
            for identity_id, identity in self.identities.items():
                traits = identity["traits"]
                if body["identifier"] in (traits.get("handle"), traits.get("email")):
                    if self.passwords[identity_id] != body["password"]:
                        break
                    self.logins.append(identity_id)
                    if self.login_status is not None:
                        return httpx.Response(self.login_status, json={})
                    return httpx.Response(
                        200, json={"session_token": f"token-{identity_id}", "session": {"identity": identity}}
                    )
            return httpx.Response(400, json={"ui": {"messages": [{"id": 4000006}]}})
        return httpx.Response(404)


class FakeHost:
    """리소스마다 정한 상태를 돌려주는 게스트 호스트. 정하지 않은 리소스는 MISSING"""

    def __init__(self):
        self.statuses: dict[UUID, GuestHostStatus] = {}

    def guest_status(self, session, resource_id: UUID) -> GuestHostStatus:
        return self.statuses.get(resource_id, GuestHostStatus.MISSING)
