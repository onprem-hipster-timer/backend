"""
Cloudflare IP 관리 및 클라이언트 IP 추출

Cloudflare 프록시 환경에서 실제 클라이언트 IP를 안전하게 추출하기 위한 모듈.
Cloudflare IP 목록을 fetch하고 캐시하며, 요청이 Cloudflare에서 왔는지 검증합니다.
"""
import asyncio
import logging
import time
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

import httpx

from app.core import config as app_config

logger = logging.getLogger(__name__)

# Cloudflare 공식 IP 목록 URL
CF_IPV4_URL = "https://www.cloudflare.com/ips-v4"
CF_IPV6_URL = "https://www.cloudflare.com/ips-v6"

# HTTP 클라이언트 타임아웃
FETCH_TIMEOUT = 10.0


class CloudflareIPManager:
    """
    Cloudflare IP 목록 관리자
    
    Cloudflare 공식 URL에서 IP 목록을 fetch하고 캐시합니다.
    TTL 기반으로 캐시를 갱신하며, fetch 실패 시 이전 캐시를 사용합니다.
    """

    def __init__(self):
        self._ipv4_networks: list[IPv4Network] = []
        self._ipv6_networks: list[IPv6Network] = []
        self._last_fetch_time: float = 0
        self._fetch_lock = asyncio.Lock()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """IP 목록이 초기화되었는지 확인"""
        return self._initialized

    @property
    def is_cache_expired(self) -> bool:
        """캐시가 만료되었는지 확인"""
        if not self._initialized:
            return True
        ttl = app_config.settings.CF_IP_CACHE_TTL
        return (time.time() - self._last_fetch_time) > ttl

    async def initialize(self) -> bool:
        """
        Cloudflare IP 목록 초기화
        
        앱 시작 시 호출됩니다. fetch 실패 시 False 반환.
        
        :return: 초기화 성공 여부
        """
        return await self._fetch_ips()

    async def ensure_initialized(self) -> None:
        """
        IP 목록이 초기화되어 있는지 확인하고, 필요 시 갱신
        
        캐시가 만료되었으면 백그라운드에서 갱신을 시도합니다.
        """
        if not self._initialized:
            await self._fetch_ips()
        elif self.is_cache_expired:
            # 백그라운드에서 갱신 (Stale-While-Revalidate)
            asyncio.create_task(self._fetch_ips())

    async def _fetch_ips(self) -> bool:
        """
        Cloudflare IP 목록 fetch
        
        동시에 여러 요청이 fetch를 시도하지 않도록 lock 사용.
        
        :return: fetch 성공 여부
        """
        async with self._fetch_lock:
            # 다른 요청이 이미 fetch 완료했는지 확인
            if self._initialized and not self.is_cache_expired:
                return True

            try:
                async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
                    # IPv4와 IPv6 동시에 fetch
                    ipv4_resp, ipv6_resp = await asyncio.gather(
                        client.get(CF_IPV4_URL),
                        client.get(CF_IPV6_URL),
                        return_exceptions=True,
                    )

                    ipv4_networks: list[IPv4Network] = []
                    ipv6_networks: list[IPv6Network] = []

                    # IPv4 파싱
                    if isinstance(ipv4_resp, httpx.Response) and ipv4_resp.status_code == 200:
                        for line in ipv4_resp.text.strip().split("\n"):
                            line = line.strip()
                            if line:
                                try:
                                    ipv4_networks.append(ip_network(line, strict=False))
                                except ValueError:
                                    logger.warning(f"Invalid IPv4 CIDR from Cloudflare: {line}")
                    else:
                        logger.warning(f"Failed to fetch Cloudflare IPv4 IPs: {ipv4_resp}")

                    # IPv6 파싱
                    if isinstance(ipv6_resp, httpx.Response) and ipv6_resp.status_code == 200:
                        for line in ipv6_resp.text.strip().split("\n"):
                            line = line.strip()
                            if line:
                                try:
                                    ipv6_networks.append(ip_network(line, strict=False))
                                except ValueError:
                                    logger.warning(f"Invalid IPv6 CIDR from Cloudflare: {line}")
                    else:
                        logger.warning(f"Failed to fetch Cloudflare IPv6 IPs: {ipv6_resp}")

                    # 최소 하나의 네트워크라도 있으면 성공
                    if ipv4_networks or ipv6_networks:
                        self._ipv4_networks = ipv4_networks
                        self._ipv6_networks = ipv6_networks
                        self._last_fetch_time = time.time()
                        self._initialized = True
                        logger.info(
                            f"Cloudflare IP list updated: {len(ipv4_networks)} IPv4, "
                            f"{len(ipv6_networks)} IPv6 networks"
                        )
                        return True

                    # 둘 다 실패
                    logger.error("Failed to fetch any Cloudflare IP networks")
                    return False

            except Exception as e:
                logger.error(f"Error fetching Cloudflare IPs: {e}")
                return False

    def is_cloudflare_ip(self, ip_str: str) -> bool:
        """
        주어진 IP가 Cloudflare IP 대역에 속하는지 확인
        
        :param ip_str: 확인할 IP 주소 문자열
        :return: Cloudflare IP 여부
        """
        if not self._initialized:
            return False

        try:
            ip = ip_address(ip_str)
        except ValueError:
            logger.warning(f"Invalid IP address: {ip_str}")
            return False

        if isinstance(ip, IPv4Address):
            return any(ip in network for network in self._ipv4_networks)
        elif isinstance(ip, IPv6Address):
            return any(ip in network for network in self._ipv6_networks)

        return False


class TrustedProxyManager:
    """
    Trusted Proxy IP 관리자
    
    TRUSTED_PROXY_IPS 환경변수에 설정된 IP/CIDR 목록을 관리합니다.
    """

    def __init__(self):
        self._networks: list[IPv4Network | IPv6Network] = []
        self._initialized = False

    def initialize(self) -> None:
        """설정에서 Trusted Proxy IP 목록 로드"""
        trusted_ips = app_config.settings.trusted_proxy_ips
        networks: list[IPv4Network | IPv6Network] = []

        for ip_or_cidr in trusted_ips:
            try:
                networks.append(ip_network(ip_or_cidr, strict=False))
            except ValueError:
                logger.warning(f"Invalid trusted proxy IP/CIDR: {ip_or_cidr}")

        self._networks = networks
        self._initialized = True

        if networks:
            logger.info(f"Loaded {len(networks)} trusted proxy networks")

    def is_trusted_proxy(self, ip_str: str) -> bool:
        """
        주어진 IP가 Trusted Proxy인지 확인
        
        :param ip_str: 확인할 IP 주소 문자열
        :return: Trusted Proxy 여부
        """
        if not self._initialized:
            self.initialize()

        if not self._networks:
            return False

        try:
            ip = ip_address(ip_str)
        except ValueError:
            return False

        return any(ip in network for network in self._networks)


# 싱글톤 인스턴스
_cf_manager: CloudflareIPManager | None = None
_trusted_proxy_manager: TrustedProxyManager | None = None


def get_cloudflare_manager() -> CloudflareIPManager:
    """Cloudflare IP 관리자 싱글톤 반환"""
    global _cf_manager
    if _cf_manager is None:
        _cf_manager = CloudflareIPManager()
    return _cf_manager


def get_trusted_proxy_manager() -> TrustedProxyManager:
    """Trusted Proxy 관리자 싱글톤 반환"""
    global _trusted_proxy_manager
    if _trusted_proxy_manager is None:
        _trusted_proxy_manager = TrustedProxyManager()
    return _trusted_proxy_manager


def reset_managers() -> None:
    """관리자 인스턴스 초기화 (테스트용)"""
    global _cf_manager, _trusted_proxy_manager
    _cf_manager = None
    _trusted_proxy_manager = None


async def get_real_client_ip(
    request_client_host: str | None,
    cf_connecting_ip: str | None,
    x_forwarded_for: str | None,
) -> str:
    """
    실제 클라이언트 IP 추출
    
    프록시 설정에 따라 적절한 IP를 반환합니다.
    
    :param request_client_host: request.client.host (직접 연결된 IP)
    :param cf_connecting_ip: CF-Connecting-IP 헤더 값
    :param x_forwarded_for: X-Forwarded-For 헤더 값
    :return: 실제 클라이언트 IP
    """
    # 직접 연결 IP가 없으면 unknown 반환
    if not request_client_host:
        return "unknown"

    # CF_ENABLED=True: Cloudflare 모드
    if app_config.settings.CF_ENABLED:
        cf_manager = get_cloudflare_manager()
        await cf_manager.ensure_initialized()

        # Cloudflare IP에서 온 요청인지 확인
        if cf_manager.is_cloudflare_ip(request_client_host):
            # CF-Connecting-IP 헤더 신뢰
            if cf_connecting_ip:
                return cf_connecting_ip
            # 헤더가 없으면 경고 후 직접 IP 사용
            logger.warning(
                f"Request from Cloudflare IP {request_client_host} "
                "but CF-Connecting-IP header is missing"
            )

        # Cloudflare IP가 아니면 직접 IP 사용 (헤더 무시)
        return request_client_host

    # CF_ENABLED=False: Trusted Proxy 또는 Direct 모드
    trusted_proxy_manager = get_trusted_proxy_manager()

    if trusted_proxy_manager.is_trusted_proxy(request_client_host):
        # Trusted Proxy에서 온 요청: X-Forwarded-For 사용
        if x_forwarded_for:
            # X-Forwarded-For에서 첫 번째 비-프록시 IP 추출
            # 형식: "client, proxy1, proxy2" - 왼쪽이 원본 클라이언트
            ips = [ip.strip() for ip in x_forwarded_for.split(",")]
            for ip in ips:
                if ip and not trusted_proxy_manager.is_trusted_proxy(ip):
                    return ip
            # 모든 IP가 trusted proxy면 첫 번째 IP 사용
            if ips:
                return ips[0]

    # Trusted Proxy가 아니거나 설정이 비어있으면 직접 IP 사용
    return request_client_host
