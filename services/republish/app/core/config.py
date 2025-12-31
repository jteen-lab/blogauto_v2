"""
환경변수 기반 설정 관리

Features:
- Pydantic 기반 타입 안전성
- 환경별 설정 (dev/prod)
- 민감정보 보호
- 기본값 제공
"""
from pydantic_settings import BaseSettings
from pydantic import validator
from typing import Optional
import os


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # 애플리케이션 기본 설정
    app_name: str = "BlogAuto V2"
    app_version: str = "2.0.0"
    environment: str = "development"
    debug: bool = False

    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

    # 데이터베이스 설정
    database_url: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "blogauto_v2"
    db_user: str = "postgres"
    db_password: str = "password"
    db_echo: bool = False

    # 보안 설정
    secret_key: str = "your-secret-key-here-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7일
    password_hash_rounds: int = 12

    # 암호화 키 (Fernet)
    encryption_key: Optional[str] = None

    # Redis 설정 (선택적)
    redis_url: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # 로깅 설정
    log_level: str = "INFO"
    log_file_enabled: bool = True
    log_max_size: int = 10  # MB

    # API 설정
    api_v1_prefix: str = "/api/v1"
    cors_origins: list = ["http://localhost:3000", "http://localhost:8000"]

    # WordPress 관련 (추후 사용)
    wp_api_timeout: int = 30
    wp_max_retries: int = 3

    @validator("database_url", pre=True)
    def build_database_url(cls, v: Optional[str], values: dict) -> str:
        """데이터베이스 URL 생성"""
        if v:
            return v

        user = values.get("db_user")
        password = values.get("db_password")
        host = values.get("db_host")
        port = values.get("db_port")
        name = values.get("db_name")

        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

    @validator("redis_url", pre=True)
    def build_redis_url(cls, v: Optional[str], values: dict) -> str:
        """Redis URL 생성"""
        if v:
            return v

        host = values.get("redis_host")
        port = values.get("redis_port")
        db = values.get("redis_db")

        return f"redis://{host}:{port}/{db}"

    @validator("environment")
    def validate_environment(cls, v: str) -> str:
        """환경값 검증"""
        valid_envs = ["development", "testing", "production"]
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v

    @validator("secret_key")
    def validate_secret_key(cls, v: str, values: dict) -> str:
        """시크릿 키 검증"""
        environment = values.get("environment")
        if environment == "production" and v == "your-secret-key-here-change-in-production":
            raise ValueError("Must set SECRET_KEY in production environment")

        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters long")

        return v

    @property
    def is_development(self) -> bool:
        """개발 환경 여부"""
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        """운영 환경 여부"""
        return self.environment == "production"

    @property
    def is_testing(self) -> bool:
        """테스트 환경 여부"""
        return self.environment == "testing"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"  # .env 파일의 추가 변수 허용


def get_settings() -> Settings:
    """설정 객체 반환 (캐시 적용)"""
    return Settings()


# 전역 설정 객체
settings = get_settings()