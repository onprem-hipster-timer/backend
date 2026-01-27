"""
CORS 환경변수 설정 테스트
"""
import os

import pytest

from app.core.config import Settings


class TestCORSSettings:
    """CORS 설정 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 환경변수 저장 및 복원"""
        self.original_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS")
        self.original_cors_credentials = os.environ.get("CORS_ALLOW_CREDENTIALS")
        self.original_cors_methods = os.environ.get("CORS_ALLOW_METHODS")
        self.original_cors_headers = os.environ.get("CORS_ALLOW_HEADERS")
        yield
        # 복원
        if self.original_cors_origins is not None:
            os.environ["CORS_ALLOWED_ORIGINS"] = self.original_cors_origins
        else:
            os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        if self.original_cors_credentials is not None:
            os.environ["CORS_ALLOW_CREDENTIALS"] = self.original_cors_credentials
        else:
            os.environ.pop("CORS_ALLOW_CREDENTIALS", None)
        if self.original_cors_methods is not None:
            os.environ["CORS_ALLOW_METHODS"] = self.original_cors_methods
        else:
            os.environ.pop("CORS_ALLOW_METHODS", None)
        if self.original_cors_headers is not None:
            os.environ["CORS_ALLOW_HEADERS"] = self.original_cors_headers
        else:
            os.environ.pop("CORS_ALLOW_HEADERS", None)

    def test_cors_origins_default(self):
        """기본값은 모든 origin 허용"""
        os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        settings = Settings()

        assert settings.CORS_ALLOWED_ORIGINS == "*"
        assert settings.cors_origins == ["*"]

    def test_cors_origins_single_origin(self):
        """단일 origin 설정"""
        os.environ["CORS_ALLOWED_ORIGINS"] = "https://example.com"
        settings = Settings()

        assert settings.CORS_ALLOWED_ORIGINS == "https://example.com"
        assert settings.cors_origins == ["https://example.com"]

    def test_cors_origins_multiple_origins(self):
        """여러 origin 설정 (콤마 구분)"""
        os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000,https://example.com,https://app.example.com"
        settings = Settings()

        assert settings.cors_origins == [
            "http://localhost:3000",
            "https://example.com",
            "https://app.example.com"
        ]

    def test_cors_origins_with_spaces(self):
        """공백이 포함된 origin 목록 정리"""
        os.environ["CORS_ALLOWED_ORIGINS"] = " http://localhost:3000 , https://example.com , https://app.example.com "
        settings = Settings()

        assert settings.cors_origins == [
            "http://localhost:3000",
            "https://example.com",
            "https://app.example.com"
        ]

    def test_cors_origins_empty_string(self):
        """빈 문자열 처리"""
        os.environ["CORS_ALLOWED_ORIGINS"] = ""
        settings = Settings()

        assert settings.CORS_ALLOWED_ORIGINS == ""
        assert settings.cors_origins == []

    def test_cors_methods_default(self):
        """기본값은 모든 메서드 허용"""
        os.environ.pop("CORS_ALLOW_METHODS", None)
        settings = Settings()

        assert settings.CORS_ALLOW_METHODS == "*"
        assert settings.cors_methods == ["*"]

    def test_cors_methods_specific(self):
        """특정 메서드만 허용"""
        os.environ["CORS_ALLOW_METHODS"] = "GET,POST,PUT,DELETE"
        settings = Settings()

        assert settings.cors_methods == ["GET", "POST", "PUT", "DELETE"]

    def test_cors_methods_with_spaces(self):
        """공백이 포함된 메서드 목록 정리"""
        os.environ["CORS_ALLOW_METHODS"] = " GET , POST , PUT , DELETE "
        settings = Settings()

        assert settings.cors_methods == ["GET", "POST", "PUT", "DELETE"]

    def test_cors_headers_default(self):
        """기본값은 모든 헤더 허용"""
        os.environ.pop("CORS_ALLOW_HEADERS", None)
        settings = Settings()

        assert settings.CORS_ALLOW_HEADERS == "*"
        assert settings.cors_headers == ["*"]

    def test_cors_headers_specific(self):
        """특정 헤더만 허용"""
        os.environ["CORS_ALLOW_HEADERS"] = "Content-Type,Authorization,X-Requested-With"
        settings = Settings()

        assert settings.cors_headers == [
            "Content-Type",
            "Authorization",
            "X-Requested-With"
        ]

    def test_cors_headers_with_spaces(self):
        """공백이 포함된 헤더 목록 정리"""
        os.environ["CORS_ALLOW_HEADERS"] = " Content-Type , Authorization , X-Requested-With "
        settings = Settings()

        assert settings.cors_headers == [
            "Content-Type",
            "Authorization",
            "X-Requested-With"
        ]

    def test_cors_allow_credentials_default(self):
        """기본값은 credentials 허용 안 함"""
        os.environ.pop("CORS_ALLOW_CREDENTIALS", None)
        settings = Settings()

        assert settings.CORS_ALLOW_CREDENTIALS is False

    def test_cors_allow_credentials_true(self):
        """credentials 허용 설정"""
        os.environ["CORS_ALLOW_CREDENTIALS"] = "true"
        settings = Settings()

        assert settings.CORS_ALLOW_CREDENTIALS is True

    def test_cors_allow_credentials_false(self):
        """credentials 비허용 설정"""
        os.environ["CORS_ALLOW_CREDENTIALS"] = "false"
        settings = Settings()

        assert settings.CORS_ALLOW_CREDENTIALS is False

    def test_cors_all_settings_together(self):
        """모든 CORS 설정을 함께 사용"""
        os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000,https://example.com"
        os.environ["CORS_ALLOW_METHODS"] = "GET,POST,PUT"
        os.environ["CORS_ALLOW_HEADERS"] = "Content-Type,Authorization"
        os.environ["CORS_ALLOW_CREDENTIALS"] = "true"

        settings = Settings()

        assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
        assert settings.cors_methods == ["GET", "POST", "PUT"]
        assert settings.cors_headers == ["Content-Type", "Authorization"]
        assert settings.CORS_ALLOW_CREDENTIALS is True
