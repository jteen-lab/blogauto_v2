"""
비밀번호 해싱 및 검증

Features:
- bcrypt 기반 안전한 해싱
- 솔트 자동 생성
- 느린 해싱으로 브루트포스 방지
- 타이밍 공격 방지
"""
from passlib.context import CryptContext
from typing import str as String
import secrets
import time

from .config import settings
from .logger import get_logger

logger = get_logger("password")

class PasswordManager:
    """비밀번호 관리 클래스"""

    def __init__(self):
        self.pwd_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=settings.password_hash_rounds
        )

    def hash_password(self, password: str) -> str:
        """
        비밀번호 해싱

        Args:
            password: 원본 비밀번호

        Returns:
            해싱된 비밀번호
        """
        if not password:
            raise ValueError("Password cannot be empty")

        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        start_time = time.time()

        try:
            hashed = self.pwd_context.hash(password)
            duration = time.time() - start_time

            logger.info(f"비밀번호 해싱 완료 | 소요시간={duration:.3f}초")
            return hashed

        except Exception as e:
            logger.error(f"비밀번호 해싱 실패: {e}")
            raise

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        비밀번호 검증

        Args:
            plain_password: 원본 비밀번호
            hashed_password: 해싱된 비밀번호

        Returns:
            검증 결과 (True/False)
        """
        if not plain_password or not hashed_password:
            logger.warning("빈 비밀번호 검증 시도")
            # 타이밍 공격 방지를 위한 더미 연산
            self._dummy_verification()
            return False

        start_time = time.time()

        try:
            result = self.pwd_context.verify(plain_password, hashed_password)
            duration = time.time() - start_time

            logger.info(f"비밀번호 검증 | 결과={result} | 소요시간={duration:.3f}초")
            return result

        except Exception as e:
            logger.error(f"비밀번호 검증 오류: {e}")
            # 타이밍 공격 방지
            self._dummy_verification()
            return False

    def _dummy_verification(self) -> None:
        """타이밍 공격 방지용 더미 연산"""
        dummy_hash = "$2b$12$dummy.hash.to.prevent.timing.attacks"
        self.pwd_context.verify("dummy", dummy_hash)

    def needs_update(self, hashed_password: str) -> bool:
        """
        해시 업데이트 필요 여부 확인

        Args:
            hashed_password: 기존 해싱된 비밀번호

        Returns:
            업데이트 필요 여부
        """
        try:
            return self.pwd_context.needs_update(hashed_password)
        except Exception:
            return True

    def generate_random_password(self, length: int = 16) -> str:
        """
        랜덤 비밀번호 생성

        Args:
            length: 비밀번호 길이

        Returns:
            생성된 비밀번호
        """
        if length < 8:
            length = 8

        # 안전한 문자 집합
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))

        logger.info(f"랜덤 비밀번호 생성 | 길이={length}")
        return password


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """
    비밀번호 강도 검증

    Args:
        password: 검증할 비밀번호

    Returns:
        (검증결과, 오류메시지 리스트)
    """
    errors = []

    if not password:
        errors.append("비밀번호를 입력해주세요")
        return False, errors

    if len(password) < 8:
        errors.append("비밀번호는 최소 8자 이상이어야 합니다")

    if len(password) > 128:
        errors.append("비밀번호는 128자를 초과할 수 없습니다")

    if not any(c.islower() for c in password):
        errors.append("소문자를 포함해야 합니다")

    if not any(c.isupper() for c in password):
        errors.append("대문자를 포함해야 합니다")

    if not any(c.isdigit() for c in password):
        errors.append("숫자를 포함해야 합니다")

    # 일반적인 약한 비밀번호 패턴 체크
    weak_patterns = [
        "password", "123456", "qwerty", "admin", "letmein",
        "password123", "123456789", "qwerty123"
    ]

    if password.lower() in weak_patterns:
        errors.append("너무 단순한 비밀번호입니다")

    is_valid = len(errors) == 0
    return is_valid, errors


# 전역 비밀번호 매니저
password_manager = PasswordManager()

# 편의 함수들
def hash_password(password: str) -> str:
    """비밀번호 해싱"""
    return password_manager.hash_password(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return password_manager.verify_password(plain_password, hashed_password)

def generate_random_password(length: int = 16) -> str:
    """랜덤 비밀번호 생성"""
    return password_manager.generate_random_password(length)