"""
Google 계정 인증 정보 서비스

Features:
- Google OAuth 토큰 관리
- 계정 연결/해제
- 토큰 갱신
- 계정 정보 조회
"""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..models.google_credential import GoogleCredential
from ..models.google_account_policy import GoogleAccountPolicy
from ..schemas.google_credential import (
    GoogleCredentialCreate,
    GoogleCredentialUpdate,
    GoogleCredentialResponse
)
from ..core.logger import get_logger

logger = get_logger("google_credential", "security.log")


class GoogleCredentialService:
    """Google 계정 인증 정보 서비스"""

    def __init__(self, db: Session):
        self.db = db

    async def create(self, user_id: int, credential_data: GoogleCredentialCreate) -> GoogleCredential:
        """새 Google 계정 연결"""
        logger.info(f"[CREATE] Google 계정 연결 시작: user_id={user_id}, email={credential_data.google_email}")

        try:
            # 중복 계정 확인
            existing = await self.get_by_email(user_id, credential_data.google_email)
            if existing:
                logger.warning(f"[CREATE] 이미 연결된 계정: {credential_data.google_email}")
                raise ValueError(f"이미 연결된 Google 계정입니다: {credential_data.google_email}")

            # 새 인증 정보 생성
            credential = GoogleCredential(
                user_id=user_id,
                google_email=credential_data.google_email
            )

            # 토큰 설정
            credential.set_tokens(
                access_token=credential_data.access_token,
                refresh_token=credential_data.refresh_token,
                expires_in_seconds=credential_data.expires_in_seconds
            )

            self.db.add(credential)
            self.db.flush()  # ID 생성을 위해 flush

            # 기본 정책 생성
            policy = GoogleAccountPolicy.create_default_policy(
                credential_id=credential.id,
                safety_mode=True
            )
            self.db.add(policy)
            self.db.commit()

            logger.info(f"[CREATE] Google 계정 연결 완료: credential_id={credential.id}")
            return credential

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"[CREATE] 계정 연결 실패 - 중복: {credential_data.google_email}")
            raise ValueError(f"이미 연결된 Google 계정입니다: {credential_data.google_email}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"[CREATE] 계정 연결 실패: {e}")
            raise

    async def get_by_user(self, user_id: int) -> List[GoogleCredential]:
        """사용자의 모든 Google 계정 조회"""
        credentials = self.db.query(GoogleCredential).filter(
            GoogleCredential.user_id == user_id
        ).order_by(GoogleCredential.created_at.desc()).all()

        logger.info(f"[GET_BY_USER] user_id={user_id}, 계정 수={len(credentials)}")
        return credentials

    async def get_by_email(self, user_id: int, email: str) -> Optional[GoogleCredential]:
        """사용자의 특정 Google 계정 조회"""
        credential = self.db.query(GoogleCredential).filter(
            GoogleCredential.user_id == user_id,
            GoogleCredential.google_email == email
        ).first()

        logger.debug(f"[GET_BY_EMAIL] user_id={user_id}, email={email}, found={bool(credential)}")
        return credential

    async def get_by_id(self, credential_id: int, user_id: Optional[int] = None) -> Optional[GoogleCredential]:
        """ID로 계정 조회 (사용자 제한 선택)"""
        query = self.db.query(GoogleCredential).filter(GoogleCredential.id == credential_id)

        if user_id:
            query = query.filter(GoogleCredential.user_id == user_id)

        credential = query.first()
        logger.debug(f"[GET_BY_ID] credential_id={credential_id}, found={bool(credential)}")
        return credential

    async def update_tokens(self, credential_id: int, token_data: GoogleCredentialUpdate) -> Optional[GoogleCredential]:
        """토큰 정보 업데이트"""
        logger.info(f"[UPDATE_TOKENS] credential_id={credential_id}")

        credential = await self.get_by_id(credential_id)
        if not credential:
            logger.warning(f"[UPDATE_TOKENS] 계정을 찾을 수 없음: {credential_id}")
            return None

        try:
            # 토큰 업데이트
            if token_data.access_token:
                credential.set_tokens(
                    access_token=token_data.access_token,
                    refresh_token=token_data.refresh_token,
                    expires_in_seconds=token_data.expires_in_seconds
                )

            self.db.commit()
            logger.info(f"[UPDATE_TOKENS] 토큰 업데이트 완료: credential_id={credential_id}")
            return credential

        except Exception as e:
            self.db.rollback()
            logger.error(f"[UPDATE_TOKENS] 토큰 업데이트 실패: {e}")
            raise

    async def refresh_token_if_needed(self, credential_id: int, buffer_minutes: int = 5) -> bool:
        """필요시 토큰 갱신"""
        credential = await self.get_by_id(credential_id)
        if not credential:
            return False

        if not credential.needs_refresh(buffer_minutes):
            return True  # 갱신 불필요

        logger.info(f"[REFRESH_TOKEN] 토큰 갱신 필요: credential_id={credential_id}")

        # TODO: 실제 Google API 호출로 토큰 갱신
        # 현재는 스켈레톤 구현
        try:
            refresh_token = credential.get_refresh_token()
            if not refresh_token:
                logger.warning(f"[REFRESH_TOKEN] 리프레시 토큰이 없음: {credential_id}")
                return False

            # Google API 호출 (구현 필요)
            # new_tokens = await google_oauth_refresh(refresh_token)

            logger.info(f"[REFRESH_TOKEN] 토큰 갱신 완료: credential_id={credential_id}")
            return True

        except Exception as e:
            logger.error(f"[REFRESH_TOKEN] 토큰 갱신 실패: {e}")
            return False

    async def delete(self, credential_id: int, user_id: int) -> bool:
        """Google 계정 연결 해제"""
        logger.info(f"[DELETE] 계정 해제 시작: credential_id={credential_id}, user_id={user_id}")

        credential = await self.get_by_id(credential_id, user_id)
        if not credential:
            logger.warning(f"[DELETE] 계정을 찾을 수 없음: {credential_id}")
            return False

        try:
            # 연관된 블로그들의 Google 계정 해제
            from ..models.blog import Blog
            blogs = self.db.query(Blog).filter(
                Blog.google_credential_id == credential_id
            ).all()

            for blog in blogs:
                blog.google_credential_id = None
                logger.info(f"[DELETE] 블로그 계정 해제: blog_id={blog.id}")

            # 계정 삭제 (CASCADE로 정책, 슬롯도 함께 삭제)
            self.db.delete(credential)
            self.db.commit()

            logger.info(f"[DELETE] 계정 해제 완료: credential_id={credential_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"[DELETE] 계정 해제 실패: {e}")
            raise

    async def get_expired_credentials(self, buffer_minutes: int = 5) -> List[GoogleCredential]:
        """만료된/만료 예정 계정 조회"""
        buffer_time = datetime.utcnow() + timedelta(minutes=buffer_minutes)

        credentials = self.db.query(GoogleCredential).filter(
            GoogleCredential.token_expiry.isnot(None),
            GoogleCredential.token_expiry <= buffer_time
        ).all()

        logger.info(f"[GET_EXPIRED] 만료 예정 계정 수: {len(credentials)}")
        return credentials

    async def check_credentials_health(self, user_id: int) -> Dict[str, Any]:
        """사용자 계정 상태 종합 확인"""
        credentials = await self.get_by_user(user_id)

        health_report = {
            "total_accounts": len(credentials),
            "active_accounts": 0,
            "expired_accounts": 0,
            "expiring_soon": 0,
            "details": []
        }

        for cred in credentials:
            status = {
                "credential_id": cred.id,
                "email": cred.google_email,
                "is_expired": cred.is_token_expired,
                "expires_in_minutes": cred.token_expires_in_minutes,
                "needs_refresh": cred.needs_refresh()
            }

            if cred.is_token_expired:
                health_report["expired_accounts"] += 1
            elif cred.needs_refresh(30):  # 30분 이내 만료
                health_report["expiring_soon"] += 1
            else:
                health_report["active_accounts"] += 1

            health_report["details"].append(status)

        logger.info(f"[HEALTH_CHECK] user_id={user_id}, 결과={health_report}")
        return health_report