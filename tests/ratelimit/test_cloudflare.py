"""
Cloudflare IP 관리 및 클라이언트 IP 추출 테스트

Cloudflare IP 검증, Trusted Proxy, 클라이언트 IP 추출 로직 테스트.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ratelimit.cloudflare import (
    CloudflareIPManager,
    TrustedProxyManager,
    get_real_client_ip,
    reset_managers,
)
from app.ratelimit.exceptions import ProxyEnforcementError

pytestmark = pytest.mark.ratelimit


class TestCloudflareIPManager:
    """Cloudflare IP 관리자 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 관리자 초기화"""
        reset_managers()
        yield
        reset_managers()

    @pytest.fixture
    def mock_cf_response(self):
        """Cloudflare IP 응답 모킹"""
        ipv4_content = "173.245.48.0/20\n103.21.244.0/22\n103.22.200.0/22"
        ipv6_content = "2400:cb00::/32\n2606:4700::/32"

        def create_response(url):
            response = AsyncMock(spec=httpx.Response)
            response.status_code = 200
            if "ips-v4" in url:
                response.text = ipv4_content
            else:
                response.text = ipv6_content
            return response

        return create_response

    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_cf_response):
        """IP 목록 초기화 성공"""
        manager = CloudflareIPManager()

        with patch("app.ratelimit.cloudflare.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get = AsyncMock(side_effect=mock_cf_response)

            success = await manager.initialize()

        assert success is True
        assert manager.is_initialized is True

    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        """IP 목록 초기화 실패"""
        manager = CloudflareIPManager()

        with patch("app.ratelimit.cloudflare.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))

            success = await manager.initialize()

        assert success is False
        assert manager.is_initialized is False

    @pytest.mark.asyncio
    async def test_is_cloudflare_ip_ipv4(self, mock_cf_response):
        """IPv4 Cloudflare IP 확인"""
        manager = CloudflareIPManager()

        with patch("app.ratelimit.cloudflare.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get = AsyncMock(side_effect=mock_cf_response)
            await manager.initialize()

        # Cloudflare IP 범위 내
        assert manager.is_cloudflare_ip("173.245.48.1") is True
        assert manager.is_cloudflare_ip("103.21.244.100") is True

        # Cloudflare IP 범위 외
        assert manager.is_cloudflare_ip("8.8.8.8") is False
        assert manager.is_cloudflare_ip("192.168.1.1") is False

    @pytest.mark.asyncio
    async def test_is_cloudflare_ip_ipv6(self, mock_cf_response):
        """IPv6 Cloudflare IP 확인"""
        manager = CloudflareIPManager()

        with patch("app.ratelimit.cloudflare.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get = AsyncMock(side_effect=mock_cf_response)
            await manager.initialize()

        # Cloudflare IP 범위 내
        assert manager.is_cloudflare_ip("2400:cb00::1") is True
        assert manager.is_cloudflare_ip("2606:4700::1") is True

        # Cloudflare IP 범위 외
        assert manager.is_cloudflare_ip("2001:4860:4860::8888") is False

    def test_is_cloudflare_ip_not_initialized(self):
        """초기화 안된 상태에서는 항상 False"""
        manager = CloudflareIPManager()

        assert manager.is_cloudflare_ip("173.245.48.1") is False

    def test_is_cloudflare_ip_invalid(self, mock_cf_response):
        """잘못된 IP 형식"""
        manager = CloudflareIPManager()

        # 초기화 없이도 invalid IP는 False
        assert manager.is_cloudflare_ip("invalid-ip") is False
        assert manager.is_cloudflare_ip("") is False


class TestTrustedProxyManager:
    """Trusted Proxy 관리자 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 관리자 초기화"""
        reset_managers()
        yield
        reset_managers()

    def test_is_trusted_proxy_single_ip(self):
        """단일 IP 신뢰 확인"""
        os.environ["TRUSTED_PROXY_IPS"] = "127.0.0.1"

        # settings 재로드
        from app.core.config import Settings
        import app.core.config as config_module
        original_settings = config_module.settings
        config_module.settings = Settings()

        try:
            manager = TrustedProxyManager()
            manager.initialize()

            assert manager.is_trusted_proxy("127.0.0.1") is True
            assert manager.is_trusted_proxy("192.168.1.1") is False
        finally:
            os.environ.pop("TRUSTED_PROXY_IPS", None)
            config_module.settings = original_settings

    def test_is_trusted_proxy_cidr(self):
        """CIDR 범위 신뢰 확인"""
        os.environ["TRUSTED_PROXY_IPS"] = "10.0.0.0/8,192.168.0.0/16"

        from app.core.config import Settings
        import app.core.config as config_module
        original_settings = config_module.settings
        config_module.settings = Settings()

        try:
            manager = TrustedProxyManager()
            manager.initialize()

            assert manager.is_trusted_proxy("10.0.0.1") is True
            assert manager.is_trusted_proxy("10.255.255.255") is True
            assert manager.is_trusted_proxy("192.168.1.100") is True
            assert manager.is_trusted_proxy("172.16.0.1") is False
        finally:
            os.environ.pop("TRUSTED_PROXY_IPS", None)
            config_module.settings = original_settings

    def test_is_trusted_proxy_empty(self):
        """빈 설정시 모든 IP 불신"""
        os.environ["TRUSTED_PROXY_IPS"] = ""

        from app.core.config import Settings
        import app.core.config as config_module
        original_settings = config_module.settings
        config_module.settings = Settings()

        try:
            manager = TrustedProxyManager()
            manager.initialize()

            assert manager.is_trusted_proxy("127.0.0.1") is False
            assert manager.is_trusted_proxy("10.0.0.1") is False
        finally:
            os.environ.pop("TRUSTED_PROXY_IPS", None)
            config_module.settings = original_settings


class TestGetRealClientIP:
    """get_real_client_ip 함수 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 관리자 및 환경 초기화"""
        reset_managers()
        self.original_cf_enabled = os.environ.get("CF_ENABLED")
        self.original_trusted_ips = os.environ.get("TRUSTED_PROXY_IPS")
        yield
        reset_managers()
        if self.original_cf_enabled is not None:
            os.environ["CF_ENABLED"] = self.original_cf_enabled
        else:
            os.environ.pop("CF_ENABLED", None)
        if self.original_trusted_ips is not None:
            os.environ["TRUSTED_PROXY_IPS"] = self.original_trusted_ips
        else:
            os.environ.pop("TRUSTED_PROXY_IPS", None)

    @pytest.mark.asyncio
    async def test_cf_disabled_no_trusted_proxy(self):
        """CF 비활성화, Trusted Proxy 없음 -> 직접 IP 사용"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["TRUSTED_PROXY_IPS"] = ""

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        result = await get_real_client_ip(
            request_client_host="1.2.3.4",
            cf_connecting_ip="5.6.7.8",
            x_forwarded_for="9.10.11.12",
        )

        # 모든 헤더 무시, 직접 IP 사용
        assert result == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_cf_disabled_with_trusted_proxy(self):
        """CF 비활성화, Trusted Proxy 설정 -> X-Forwarded-For 사용"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["TRUSTED_PROXY_IPS"] = "10.0.0.1"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        result = await get_real_client_ip(
            request_client_host="10.0.0.1",  # Trusted Proxy
            cf_connecting_ip=None,
            x_forwarded_for="203.0.113.50, 10.0.0.1",
        )

        # X-Forwarded-For에서 첫 번째 비-프록시 IP
        assert result == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_cf_disabled_untrusted_client(self):
        """CF 비활성화, 클라이언트가 Trusted Proxy가 아님 -> 직접 IP 사용"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["TRUSTED_PROXY_IPS"] = "10.0.0.1"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        result = await get_real_client_ip(
            request_client_host="203.0.113.100",  # Not trusted
            cf_connecting_ip=None,
            x_forwarded_for="1.2.3.4",  # 무시됨
        )

        # 직접 IP 사용 (X-Forwarded-For 무시)
        assert result == "203.0.113.100"

    @pytest.mark.asyncio
    async def test_cf_enabled_from_cloudflare(self):
        """CF 활성화, Cloudflare IP에서 요청 -> CF-Connecting-IP 사용"""
        os.environ["CF_ENABLED"] = "true"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        # Cloudflare IP 매니저 모킹 (is_cloudflare_ip는 동기 메서드)
        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            mock_manager.is_cloudflare_ip.return_value = True
            mock_get_manager.return_value = mock_manager

            result = await get_real_client_ip(
                request_client_host="173.245.48.1",  # Cloudflare IP
                cf_connecting_ip="203.0.113.50",
                x_forwarded_for="fake-ip",
            )

        assert result == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_cf_enabled_not_from_cloudflare(self):
        """CF 활성화, Cloudflare가 아닌 IP에서 요청 -> 직접 IP 사용"""
        os.environ["CF_ENABLED"] = "true"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            mock_manager.is_cloudflare_ip.return_value = False
            mock_get_manager.return_value = mock_manager

            result = await get_real_client_ip(
                request_client_host="8.8.8.8",  # Not Cloudflare
                cf_connecting_ip="spoofed-ip",  # 무시됨
                x_forwarded_for="fake-ip",  # 무시됨
            )

        # Cloudflare가 아니면 직접 IP 사용
        assert result == "8.8.8.8"

    @pytest.mark.asyncio
    async def test_cf_enabled_missing_header(self):
        """CF 활성화, Cloudflare IP지만 헤더 없음 -> 직접 IP 사용"""
        os.environ["CF_ENABLED"] = "true"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            mock_manager.is_cloudflare_ip.return_value = True
            mock_get_manager.return_value = mock_manager

            result = await get_real_client_ip(
                request_client_host="173.245.48.1",
                cf_connecting_ip=None,  # 헤더 없음
                x_forwarded_for=None,
            )

        # 헤더 없으면 직접 IP 사용
        assert result == "173.245.48.1"

    @pytest.mark.asyncio
    async def test_proxy_force_cf_blocks_non_cloudflare_source(self):
        """PROXY_FORCE + CF_ENABLED: Cloudflare IP가 아니면 차단"""
        os.environ["CF_ENABLED"] = "true"
        os.environ["PROXY_FORCE"] = "true"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            mock_manager.is_cloudflare_ip.return_value = False
            mock_get_manager.return_value = mock_manager

            with pytest.raises(ProxyEnforcementError):
                await get_real_client_ip(
                    request_client_host="8.8.8.8",
                    cf_connecting_ip="203.0.113.50",
                    x_forwarded_for=None,
                )

    @pytest.mark.asyncio
    async def test_proxy_force_cf_allows_cloudflare_source_and_uses_header(self):
        """PROXY_FORCE + CF_ENABLED: Cloudflare IP면 통과, CF-Connecting-IP 사용"""
        os.environ["CF_ENABLED"] = "true"
        os.environ["PROXY_FORCE"] = "true"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            mock_manager.is_cloudflare_ip.return_value = True
            mock_get_manager.return_value = mock_manager

            result = await get_real_client_ip(
                request_client_host="173.245.48.1",
                cf_connecting_ip="203.0.113.50",
                x_forwarded_for=None,
            )

        assert result == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_proxy_force_trusted_proxy_blocks_untrusted_source(self):
        """PROXY_FORCE + CF_DISABLED: Trusted Proxy가 아니면 차단"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["PROXY_FORCE"] = "true"
        os.environ["TRUSTED_PROXY_IPS"] = "10.0.0.1"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with pytest.raises(ProxyEnforcementError):
            await get_real_client_ip(
                request_client_host="203.0.113.100",
                cf_connecting_ip=None,
                x_forwarded_for="203.0.113.50, 10.0.0.1",
            )

    @pytest.mark.asyncio
    async def test_proxy_force_trusted_proxy_allows_trusted_source_and_uses_xff(self):
        """PROXY_FORCE + CF_DISABLED: Trusted Proxy면 통과, X-Forwarded-For 사용"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["PROXY_FORCE"] = "true"
        os.environ["TRUSTED_PROXY_IPS"] = "10.0.0.1"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        result = await get_real_client_ip(
            request_client_host="10.0.0.1",
            cf_connecting_ip=None,
            x_forwarded_for="203.0.113.50, 10.0.0.1",
        )

        assert result == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_no_client_host(self):
        """클라이언트 호스트 없음 -> unknown 반환"""
        result = await get_real_client_ip(
            request_client_host=None,
            cf_connecting_ip="1.2.3.4",
            x_forwarded_for="5.6.7.8",
        )

        assert result == "unknown"


class TestSpoofingPrevention:
    """스푸핑 방지 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 초기화"""
        reset_managers()
        self.original_cf_enabled = os.environ.get("CF_ENABLED")
        self.original_trusted_ips = os.environ.get("TRUSTED_PROXY_IPS")
        self.original_proxy_force = os.environ.get("PROXY_FORCE")
        yield
        reset_managers()
        if self.original_cf_enabled is not None:
            os.environ["CF_ENABLED"] = self.original_cf_enabled
        else:
            os.environ.pop("CF_ENABLED", None)
        if self.original_trusted_ips is not None:
            os.environ["TRUSTED_PROXY_IPS"] = self.original_trusted_ips
        else:
            os.environ.pop("TRUSTED_PROXY_IPS", None)
        if self.original_proxy_force is not None:
            os.environ["PROXY_FORCE"] = self.original_proxy_force
        else:
            os.environ.pop("PROXY_FORCE", None)

    @pytest.mark.asyncio
    async def test_cannot_spoof_cf_connecting_ip(self):
        """공격자가 CF-Connecting-IP 헤더를 스푸핑해도 무시됨"""
        os.environ["CF_ENABLED"] = "true"
        os.environ["PROXY_FORCE"] = "false"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        with patch("app.ratelimit.cloudflare.get_cloudflare_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.ensure_initialized = AsyncMock()
            # 공격자 IP는 Cloudflare가 아님
            mock_manager.is_cloudflare_ip.return_value = False
            mock_get_manager.return_value = mock_manager

            result = await get_real_client_ip(
                request_client_host="attacker-ip",  # 실제 공격자 IP
                cf_connecting_ip="victim-ip",  # 스푸핑된 헤더
                x_forwarded_for="another-victim",
            )

        # 스푸핑된 헤더 무시, 실제 IP 사용
        assert result == "attacker-ip"

    @pytest.mark.asyncio
    async def test_cannot_spoof_x_forwarded_for_without_trusted_proxy(self):
        """Trusted Proxy 없이 X-Forwarded-For 스푸핑 불가"""
        os.environ["CF_ENABLED"] = "false"
        os.environ["TRUSTED_PROXY_IPS"] = ""
        os.environ["PROXY_FORCE"] = "false"

        from app.core.config import Settings
        import app.core.config as config_module
        config_module.settings = Settings()

        result = await get_real_client_ip(
            request_client_host="attacker-ip",
            cf_connecting_ip=None,
            x_forwarded_for="spoofed-ip, another-spoofed",
        )

        # 스푸핑된 헤더 무시
        assert result == "attacker-ip"
