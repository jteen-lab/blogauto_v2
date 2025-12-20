"""
요청/응답 로깅 미들웨어

Features:
- 모든 HTTP 요청 로깅
- 응답 시간 측정
- 에러 로깅
- IP 추적
"""
import time
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import uuid

from ..core.logger import get_logger, log_request_info

logger = get_logger("request", "request.log")
error_logger = get_logger("error", "error.log")

class LoggingMiddleware(BaseHTTPMiddleware):
    """HTTP 요청 로깅 미들웨어"""

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        요청 처리 및 로깅

        Args:
            request: FastAPI 요청 객체
            call_next: 다음 미들웨어/엔드포인트

        Returns:
            처리된 응답
        """
        # 요청 ID 생성
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # 클라이언트 정보 추출
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "Unknown")
        method = request.method
        url_path = str(request.url.path)

        # 요청 시작 로깅
        start_time = time.time()

        log_request_info(
            logger,
            method=method,
            url=url_path,
            ip=client_ip,
            user_agent=user_agent
        )

        logger.info(
            f"요청시작 | ID={request_id} | {method} {url_path} | "
            f"IP={client_ip} | UA={user_agent[:50]}{'...' if len(user_agent) > 50 else ''}"
        )

        try:
            # 요청 처리
            response = await call_next(request)

            # 처리 시간 계산
            process_time = time.time() - start_time

            # 응답 로깅
            logger.info(
                f"요청완료 | ID={request_id} | {method} {url_path} | "
                f"Status={response.status_code} | 처리시간={process_time:.3f}초"
            )

            # 응답 헤더에 요청 ID 추가
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            return response

        except Exception as e:
            # 처리 시간 계산
            process_time = time.time() - start_time

            # 에러 로깅
            error_logger.error(
                f"요청에러 | ID={request_id} | {method} {url_path} | "
                f"IP={client_ip} | 처리시간={process_time:.3f}초 | 오류={str(e)}"
            )

            # 500 에러 응답 반환
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "서버 내부 오류가 발생했습니다",
                    "request_id": request_id
                },
                headers={
                    "X-Request-ID": request_id,
                    "X-Process-Time": f"{process_time:.3f}"
                }
            )

    def _get_client_ip(self, request: Request) -> str:
        """
        클라이언트 실제 IP 주소 추출

        프록시나 로드밸런서를 고려한 IP 추출

        Args:
            request: FastAPI 요청 객체

        Returns:
            클라이언트 IP 주소
        """
        # X-Forwarded-For 헤더 확인 (프록시 환경)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # 첫 번째 IP가 실제 클라이언트 IP
            return forwarded_for.split(",")[0].strip()

        # X-Real-IP 헤더 확인 (Nginx 등)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # CF-Connecting-IP 헤더 확인 (Cloudflare)
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()

        # 기본 클라이언트 IP
        return request.client.host if request.client else "unknown"