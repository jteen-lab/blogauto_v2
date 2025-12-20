"""
양방향 암호화 및 보안 유틸리티

Features:
- Fernet 기반 대칭키 암호화
- API 키 암호화
- 민감정보 보호
- 키 관리
"""
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import secrets
import os
from typing import Optional, Union

from .config import settings
from .logger import get_logger

logger = get_logger("security")

class SecurityManager:
    """보안 관리 클래스"""

    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._init_encryption()

    def _init_encryption(self) -> None:
        """암호화 키 초기화"""
        try:
            if settings.encryption_key:
                # 환경변수에서 키 로드
                key = settings.encryption_key.encode()
            else:
                # 새 키 생성 (개발환경)
                key = Fernet.generate_key()
                logger.warning("새로운 암호화 키 생성됨 - 환경변수 ENCRYPTION_KEY 설정 권장")

            self._fernet = Fernet(key)
            logger.info("암호화 시스템 초기화 완료")

        except Exception as e:
            logger.error(f"암호화 시스템 초기화 실패: {e}")
            raise

    def encrypt(self, data: str) -> str:
        """
        데이터 암호화

        Args:
            data: 암호화할 문자열

        Returns:
            암호화된 데이터 (base64 인코딩)
        """
        if not data:
            raise ValueError("암호화할 데이터가 없습니다")

        try:
            encrypted_data = self._fernet.encrypt(data.encode())
            encoded_data = base64.urlsafe_b64encode(encrypted_data).decode()

            logger.debug(f"데이터 암호화 완료 | 원본길이={len(data)} | 암호화길이={len(encoded_data)}")
            return encoded_data

        except Exception as e:
            logger.error(f"데이터 암호화 실패: {e}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """
        데이터 복호화

        Args:
            encrypted_data: 암호화된 데이터 (base64 인코딩)

        Returns:
            복호화된 원본 데이터
        """
        if not encrypted_data:
            raise ValueError("복호화할 데이터가 없습니다")

        try:
            decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self._fernet.decrypt(decoded_data)
            original_data = decrypted_data.decode()

            logger.debug(f"데이터 복호화 완료 | 암호화길이={len(encrypted_data)} | 원본길이={len(original_data)}")
            return original_data

        except Exception as e:
            logger.error(f"데이터 복호화 실패: {e}")
            raise

    def encrypt_wordpress_key(self, wp_key: str, blog_name: str) -> str:
        """
        워드프레스 API 키 암호화

        Args:
            wp_key: 워드프레스 API 키
            blog_name: 블로그 이름 (로깅용)

        Returns:
            암호화된 API 키
        """
        try:
            encrypted_key = self.encrypt(wp_key)
            logger.info(f"워드프레스 키 암호화 | 블로그={blog_name}")
            return encrypted_key

        except Exception as e:
            logger.error(f"워드프레스 키 암호화 실패 | 블로그={blog_name} | 오류={e}")
            raise

    def decrypt_wordpress_key(self, encrypted_key: str, blog_name: str) -> str:
        """
        워드프레스 API 키 복호화

        Args:
            encrypted_key: 암호화된 API 키
            blog_name: 블로그 이름 (로깅용)

        Returns:
            원본 API 키
        """
        try:
            wp_key = self.decrypt(encrypted_key)
            logger.info(f"워드프레스 키 복호화 | 블로그={blog_name}")
            return wp_key

        except Exception as e:
            logger.error(f"워드프레스 키 복호화 실패 | 블로그={blog_name} | 오류={e}")
            raise

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        안전한 랜덤 토큰 생성

        Args:
            length: 토큰 길이

        Returns:
            생성된 토큰 (hex)
        """
        token = secrets.token_hex(length)
        logger.debug(f"보안 토큰 생성 | 길이={length*2}")
        return token

    @staticmethod
    def generate_encryption_key() -> str:
        """새 암호화 키 생성"""
        key = Fernet.generate_key()
        logger.info("새 암호화 키 생성")
        return key.decode()

    @staticmethod
    def derive_key_from_password(password: str, salt: bytes = None) -> bytes:
        """
        비밀번호에서 암호화 키 유도

        Args:
            password: 비밀번호
            salt: 솔트 (미지정시 생성)

        Returns:
            유도된 키
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key


def mask_sensitive_data(data: str, show_chars: int = 4) -> str:
    """
    민감한 데이터 마스킹

    Args:
        data: 마스킹할 데이터
        show_chars: 보여줄 문자 수

    Returns:
        마스킹된 데이터
    """
    if not data or len(data) <= show_chars:
        return "*" * len(data) if data else ""

    visible = data[:show_chars]
    masked = "*" * (len(data) - show_chars)
    return f"{visible}{masked}"


def sanitize_filename(filename: str) -> str:
    """
    파일명 안전화

    Args:
        filename: 원본 파일명

    Returns:
        안전한 파일명
    """
    import re

    # 위험한 문자 제거
    sanitized = re.sub(r'[^\w\s\-_\.]', '', filename)

    # 공백을 언더스코어로 변환
    sanitized = re.sub(r'\s+', '_', sanitized)

    # 연속된 언더스코어 정리
    sanitized = re.sub(r'_{2,}', '_', sanitized)

    # 앞뒤 언더스코어 제거
    sanitized = sanitized.strip('_')

    return sanitized[:255]  # 파일명 길이 제한


# 전역 보안 매니저
security_manager = SecurityManager()

# 편의 함수들
def encrypt_data(data: str) -> str:
    """데이터 암호화"""
    return security_manager.encrypt(data)

def decrypt_data(encrypted_data: str) -> str:
    """데이터 복호화"""
    return security_manager.decrypt(encrypted_data)

def encrypt_wordpress_key(wp_key: str, blog_name: str) -> str:
    """워드프레스 키 암호화"""
    return security_manager.encrypt_wordpress_key(wp_key, blog_name)

def decrypt_wordpress_key(encrypted_key: str, blog_name: str) -> str:
    """워드프레스 키 복호화"""
    return security_manager.decrypt_wordpress_key(encrypted_key, blog_name)

def generate_secure_token(length: int = 32) -> str:
    """안전한 토큰 생성"""
    return SecurityManager.generate_secure_token(length)