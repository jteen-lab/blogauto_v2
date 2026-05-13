"""
중앙 인증 게이트 미들웨어 — Phase C 후행 추가용 자리 (지금은 pass-through).

[설계 의도]
배포 우선 전략(docs/plans/deployment_first_strategy.md § 5-A)에 따라
인증 시스템은 차후 도입 예정. 이 파일은 인증을 켤 때 코드 재배치 없이
환경변수 토글(CENTRAL_AUTH_ENABLED=true)만으로 활성화되도록 자리만 마련.

[향후 동작 (Phase C)]
1. Authorization 헤더 또는 쿠키에서 JWT 추출
2. 중앙 서버(CENTRAL_AUTH_URL)의 공개키로 검증
3. JWT payload의 grade/expires_at 확인
4. 만료/취소된 경우 401
5. request.state.user 에 사용자 정보 주입

현재는 모든 요청을 그대로 통과시킴.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.config import settings


class CentralAuthGateMiddleware(BaseHTTPMiddleware):
    """중앙 인증 게이트 — 비활성 시 pass-through."""

    async def dispatch(self, request: Request, call_next):
        if not settings.central_auth_enabled:
            return await call_next(request)

        # Phase C 후행: 여기에 JWT 검증 로직 추가 예정
        # - Authorization 헤더 파싱
        # - 중앙 서버 공개키로 RS256 검증
        # - grade/expires_at 체크
        # - request.state.user 주입
        # 지금은 활성화되어도 통과만 함 (안전한 default)
        return await call_next(request)
