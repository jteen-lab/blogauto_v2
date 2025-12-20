"""
JWT 토큰 관리

Features:
- 토큰 생성 및 검증
- 만료 시간 관리
- 안전한 쿠키 설정
- 토큰 무효화 (블랙리스트)
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from fastapi import HTTPException, status
import time

from .config import settings
from .logger import get_logger

logger = get_logger("jwt")

class JWTManager:
    """JWT 토큰 관리 클래스"""

    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = settings.jwt_algorithm
        self.expire_minutes = settings.jwt_expire_minutes

        # 토큰 블랙리스트 (Redis 사용 전까지 메모리 사용)
        self._blacklist: set[str] = set()

    def create_access_token(self, data: Dict[str, Any],
                          expires_delta: Optional[timedelta] = None) -> str:
        """
        액세스 토큰 생성

        Args:
            data: 토큰에 포함할 데이터
            expires_delta: 만료 시간 (기본값: 설정값 사용)

        Returns:
            생성된 JWT 토큰
        """
        to_encode = data.copy()

        # 만료 시간 설정
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.expire_minutes)

        # JWT 페이로드 구성
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        })

        try:
            token = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

            logger.info(f"JWT 토큰 생성 | 사용자={data.get('sub')} | 만료={expire.isoformat()}")
            return token

        except Exception as e:
            logger.error(f"JWT 토큰 생성 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="토큰 생성에 실패했습니다"
            )

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        토큰 검증 및 페이로드 반환

        Args:
            token: 검증할 JWT 토큰

        Returns:
            토큰 페이로드

        Raises:
            HTTPException: 토큰이 유효하지 않은 경우
        """
        try:
            # 블랙리스트 확인
            if self._is_blacklisted(token):
                logger.warning("블랙리스트 토큰 사용 시도")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="토큰이 무효화되었습니다"
                )

            # 토큰 디코딩
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # 토큰 타입 확인
            token_type = payload.get("type")
            if token_type != "access":
                logger.warning(f"잘못된 토큰 타입: {token_type}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="잘못된 토큰 타입입니다"
                )

            user_id = payload.get("sub")
            logger.info(f"JWT 토큰 검증 성공 | 사용자={user_id}")

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("만료된 토큰 사용 시도")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="토큰이 만료되었습니다"
            )

        except JWTError as e:
            logger.error(f"JWT 토큰 검증 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="유효하지 않은 토큰입니다"
            )

    def blacklist_token(self, token: str) -> None:
        """
        토큰 블랙리스트에 추가

        Args:
            token: 무효화할 토큰
        """
        try:
            # 토큰에서 만료 시간 추출
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}  # 만료된 토큰도 허용
            )

            # 이미 만료된 토큰은 블랙리스트에 추가하지 않음
            exp_timestamp = payload.get("exp")
            if exp_timestamp and exp_timestamp < time.time():
                logger.info("이미 만료된 토큰 - 블랙리스트 추가 생략")
                return

            self._blacklist.add(token)
            user_id = payload.get("sub")
            logger.info(f"토큰 블랙리스트 추가 | 사용자={user_id}")

        except Exception as e:
            logger.error(f"토큰 블랙리스트 추가 실패: {e}")

    def _is_blacklisted(self, token: str) -> bool:
        """토큰 블랙리스트 확인"""
        return token in self._blacklist

    def get_token_info(self, token: str) -> Dict[str, Any]:
        """
        토큰 정보 조회 (검증 없이)

        Args:
            token: 조회할 토큰

        Returns:
            토큰 정보
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )

            exp_timestamp = payload.get("exp")
            iat_timestamp = payload.get("iat")

            return {
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "issued_at": datetime.fromtimestamp(iat_timestamp) if iat_timestamp else None,
                "expires_at": datetime.fromtimestamp(exp_timestamp) if exp_timestamp else None,
                "is_expired": exp_timestamp < time.time() if exp_timestamp else False,
                "is_blacklisted": self._is_blacklisted(token)
            }

        except Exception as e:
            logger.error(f"토큰 정보 조회 실패: {e}")
            return {}

    def cleanup_blacklist(self) -> None:
        """만료된 토큰을 블랙리스트에서 제거"""
        current_time = time.time()
        expired_tokens = []

        for token in self._blacklist:
            try:
                payload = jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=[self.algorithm],
                    options={"verify_exp": False}
                )

                exp_timestamp = payload.get("exp")
                if exp_timestamp and exp_timestamp < current_time:
                    expired_tokens.append(token)

            except Exception:
                # 잘못된 토큰은 제거
                expired_tokens.append(token)

        for token in expired_tokens:
            self._blacklist.discard(token)

        if expired_tokens:
            logger.info(f"만료된 토큰 {len(expired_tokens)}개 블랙리스트에서 제거")


# 전역 JWT 매니저
jwt_manager = JWTManager()

# 편의 함수들
def create_access_token(data: Dict[str, Any],
                       expires_delta: Optional[timedelta] = None) -> str:
    """액세스 토큰 생성"""
    return jwt_manager.create_access_token(data, expires_delta)

def verify_token(token: str) -> Dict[str, Any]:
    """토큰 검증"""
    return jwt_manager.verify_token(token)

def blacklist_token(token: str) -> None:
    """토큰 무효화"""
    return jwt_manager.blacklist_token(token)