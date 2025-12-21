"""
암호화/복호화 유틸리티

Features:
- API 키 암호화/복호화
- 환경 변수 기반 암호화 키
- 안전한 키 저장
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .logger import get_logger

logger = get_logger("encryption", "security.log")


def get_encryption_key() -> bytes:
    """암호화 키 생성/조회"""
    # 환경 변수에서 키 조회
    env_key = os.environ.get("ENCRYPTION_KEY")

    if env_key:
        return base64.urlsafe_b64decode(env_key.encode())

    # 키가 없으면 경고 로그 (개발 환경용 임시 키 사용)
    logger.warning("ENCRYPTION_KEY 환경변수가 설정되지 않았습니다. 임시 키를 사용합니다.")

    # 개발용 임시 키 (실제 운영에서는 절대 사용하지 말 것!)
    temp_password = b"development_temp_key_do_not_use_in_production"
    salt = b"temp_salt_12345"  # 실제로는 랜덤 생성해야 함

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )

    return base64.urlsafe_b64encode(kdf.derive(temp_password))


def encrypt_api_key(api_key: str) -> str:
    """API 키 암호화"""
    try:
        if not api_key:
            return ""

        key = get_encryption_key()
        fernet = Fernet(key)

        encrypted = fernet.encrypt(api_key.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    except Exception as e:
        logger.error(f"API 키 암호화 실패: {e}")
        raise


def decrypt_api_key(encrypted_api_key: str) -> str:
    """API 키 복호화"""
    try:
        if not encrypted_api_key:
            return ""

        key = get_encryption_key()
        fernet = Fernet(key)

        encrypted_bytes = base64.urlsafe_b64decode(encrypted_api_key.encode())
        decrypted = fernet.decrypt(encrypted_bytes)

        return decrypted.decode()

    except Exception as e:
        logger.error(f"API 키 복호화 실패: ***")  # 실제 키는 로그에 기록하지 않음
        raise ValueError("API 키 복호화에 실패했습니다")


def generate_encryption_key() -> str:
    """새로운 암호화 키 생성 (설정용)"""
    key = Fernet.generate_key()
    return base64.urlsafe_b64encode(key).decode()