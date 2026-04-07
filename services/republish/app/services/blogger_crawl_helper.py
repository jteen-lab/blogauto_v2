"""
Blogger 크롤링 헬퍼

CrawlService에서 사용하는 Blogger API 관련 헬퍼 함수들입니다.
Blogger ID 다단계 탐색, OAuth 토큰 획득, 인증 방식 결정을 담당합니다.

기존 BloggerPublisher._extract_blog_id()와 동일한 강건성을 제공합니다.
"""
import httpx
from typing import Optional, Dict, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.blog import Blog
from ..core.security import decrypt_data
from ..core.encryption import decrypt_api_key
from ..core.logger import get_logger

logger = get_logger("blogger_crawl_helper", "crawl.log")

BLOGGER_API_BASE = "https://www.googleapis.com/blogger/v3"
REQUEST_TIMEOUT = 30.0


def get_blogger_api_key(blog: Blog) -> Optional[str]:
    """
    Blogger API 키 가져오기

    api_key_encrypted가 숫자(Blogger ID)인 경우 None을 반환합니다.
    실제 API Key("AIza..." 등)만 반환합니다.

    Args:
        blog: 블로그 객체

    Returns:
        Google API Key 문자열 또는 None
    """
    if not blog.api_key_encrypted:
        return None

    decrypted = _decrypt_field(blog.api_key_encrypted, blog.id, "API 키")
    if decrypted and not decrypted.isdigit():
        return decrypted
    return None


async def get_blogger_oauth_token(
    blog: Blog,
    db: AsyncSession,
) -> Optional[str]:
    """
    Blogger OAuth access_token 획득

    blog.oauth_token_encrypted 또는 blog.google_credential에서 토큰을 가져옵니다.
    refresh_token(1//...)인 경우 access_token으로 교환합니다.

    Args:
        blog: 블로그 객체
        db: DB 세션 (GoogleCredential 조회용)

    Returns:
        OAuth access_token 문자열 또는 None
    """
    # 1차: blog.oauth_token_encrypted
    raw_token = _get_raw_oauth_token(blog)

    if raw_token:
        # refresh_token이면 access_token으로 교환 시도
        if raw_token.startswith("1//"):
            from .publishing.google_oauth_helper import refresh_access_token
            access = await refresh_access_token(raw_token)
            if access:
                return access
            logger.warning(
                f"Blogger OAuth 토큰 갱신 실패, GoogleCredential 폴백 시도 | "
                f"블로그ID={blog.id}"
            )
        else:
            # 이미 access_token이면 그대로 반환
            return raw_token

    # 2차: GoogleCredential에서 access_token 직접 획득
    if blog.google_credential_id:
        credential_token = await _get_access_from_credential(blog, db)
        if credential_token:
            return credential_token

    logger.error(f"Blogger OAuth 토큰 획득 불가 | 블로그ID={blog.id}")
    return None


async def resolve_blogger_id(
    blog: Blog,
    api_key: Optional[str],
    oauth_token: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Blogger ID 다단계 탐색 (캐시 -> 숫자ID -> API Key -> OAuth)

    Returns:
        (blogger_id, auth_method) 튜플.
        auth_method: "cache" | "direct" | "api_key" | "oauth" | None
    """
    # 1순위: placeholders 캐시
    placeholders = blog.placeholders or {}
    cached_id = placeholders.get("blogger_id")
    if cached_id:
        logger.debug(
            f"Blogger ID 캐시 사용 | 블로그ID={blog.id} | blogger_id={cached_id}"
        )
        return str(cached_id), "cache"

    # 2순위: api_key_encrypted가 숫자이면 직접 ID
    if blog.api_key_encrypted:
        decrypted = _decrypt_field(
            blog.api_key_encrypted, blog.id, "api_key(ID 확인)"
        )
        if decrypted and decrypted.isdigit():
            logger.info(
                f"Blogger ID 직접 사용 | 블로그ID={blog.id} | blogger_id={decrypted}"
            )
            return decrypted, "direct"

    # 3순위: API Key로 blogs/byurl 호출
    if api_key and blog.url:
        blog_id = await _fetch_blogger_id_by_api_key(blog.url, api_key)
        if blog_id:
            return blog_id, "api_key"

    # 4순위: OAuth Token으로 blogs/byurl 호출
    if oauth_token and blog.url:
        blog_id = await _fetch_blogger_id_by_oauth(blog.url, oauth_token)
        if blog_id:
            return blog_id, "oauth"

    logger.error(
        f"Blogger ID 획득 실패 (모든 방법) | 블로그ID={blog.id} | "
        f"api_key={'있음' if api_key else '없음'} | "
        f"oauth_token={'있음' if oauth_token else '없음'}"
    )
    return None, None


def build_blogger_auth(
    api_key: Optional[str],
    oauth_token: Optional[str],
    auth_method: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Blogger API 인증 파라미터와 헤더를 결정

    resolve_blogger_id()에서 반환된 auth_method를 참고하여,
    실제로 성공한 인증 방식을 우선 사용합니다.

    Args:
        api_key: Google API Key (없으면 None)
        oauth_token: OAuth access_token (없으면 None)
        auth_method: resolve_blogger_id()가 반환한 성공 방식

    Returns:
        (params_dict, headers_dict) 튜플
    """
    # OAuth로 ID를 획득했으면 포스트 조회도 OAuth 사용
    if auth_method == "oauth" and oauth_token:
        logger.debug("Blogger 인증: OAuth Bearer Token (ID 획득 방식과 동일)")
        return {}, {"Authorization": f"Bearer {oauth_token}"}

    # API Key로 성공했거나, 캐시/직접ID인 경우 API Key 우선
    if api_key and auth_method in ("api_key", "cache", "direct", None):
        logger.debug("Blogger 인증: API Key 방식 사용")
        return {"key": api_key}, {}

    # 그 외 OAuth 폴백
    if oauth_token:
        logger.debug("Blogger 인증: OAuth Bearer Token 폴백")
        return {}, {"Authorization": f"Bearer {oauth_token}"}

    logger.warning("Blogger 인증: 인증 정보 없음")
    return {}, {}


# --- 내부 헬퍼 함수 ---


def _decrypt_field(
    encrypted_value: str, blog_id: int, field_name: str
) -> Optional[str]:
    """
    암호화된 필드 복호화 (decrypt_api_key → decrypt_data 폴백)

    Args:
        encrypted_value: 암호화된 문자열
        blog_id: 블로그 ID (로그용)
        field_name: 필드명 (로그용)

    Returns:
        복호화된 문자열 또는 None
    """
    # 레거시 호환: 두 가지 암호화 방식이 혼용됨
    # decrypt_api_key (Fernet) → decrypt_data (AES) 순서로 시도
    try:
        return decrypt_api_key(encrypted_value)
    except Exception:
        try:
            return decrypt_data(encrypted_value)
        except Exception as e:
            logger.warning(
                f"Blogger {field_name} 복호화 실패 | 블로그ID={blog_id} | 오류={e}"
            )
    return None


def _get_raw_oauth_token(blog: Blog) -> Optional[str]:
    """blog.oauth_token_encrypted에서 원시 토큰 추출"""
    if not blog.oauth_token_encrypted:
        return None

    return _decrypt_field(
        blog.oauth_token_encrypted, blog.id, "OAuth 토큰"
    )


async def _get_access_from_credential(
    blog: Blog, db: AsyncSession
) -> Optional[str]:
    """GoogleCredential에서 access_token 직접 획득

    credential.get_access_token() (decrypt_api_key) 실패 시
    decrypt_data 폴백을 시도합니다. 레거시 암호화 호환.
    """
    try:
        from ..models.google_credential import GoogleCredential
        credential = await db.get(GoogleCredential, blog.google_credential_id)
        if not credential or not credential.access_token_encrypted:
            return None

        # 1차: 모델 메서드 (decrypt_api_key)
        try:
            access = credential.get_access_token()
            if access:
                logger.info(
                    f"GoogleCredential access_token 획득 | "
                    f"블로그ID={blog.id} | credential_id={credential.id}"
                )
                return access
        except Exception:
            pass

        # 2차: decrypt_data 폴백 (레거시 암호화 호환)
        token = _decrypt_field(
            credential.access_token_encrypted,
            blog.id, "GoogleCredential.access_token"
        )
        if token:
            logger.info(
                f"GoogleCredential access_token 폴백 복호화 성공 | "
                f"블로그ID={blog.id} | credential_id={credential.id}"
            )
            return token
    except Exception as e:
        logger.warning(
            f"GoogleCredential 토큰 획득 실패 | "
            f"블로그ID={blog.id} | credential_id={blog.google_credential_id} | "
            f"오류={e}"
        )
    return None


async def _fetch_blogger_id_by_api_key(
    blog_url: str, api_key: str
) -> Optional[str]:
    """Google API Key로 Blogger ID 조회"""
    api_url = f"{BLOGGER_API_BASE}/blogs/byurl"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(api_url, params={
                "url": blog_url.rstrip("/"),
                "key": api_key,
            })
            if response.status_code == 200:
                blog_id = response.json().get("id")
                if blog_id:
                    logger.info(
                        f"Blogger ID (API Key) 획득 | URL={blog_url} | "
                        f"blogger_id={blog_id}"
                    )
                    return str(blog_id)
            logger.warning(
                f"Blogger ID (API Key) 실패 | URL={blog_url} | "
                f"status={response.status_code}"
            )
        except Exception as e:
            logger.error(
                f"Blogger ID (API Key) 오류 | URL={blog_url} | 오류={e}"
            )
    return None


async def _fetch_blogger_id_by_oauth(
    blog_url: str, access_token: str
) -> Optional[str]:
    """OAuth Bearer Token으로 Blogger ID 조회"""
    api_url = f"{BLOGGER_API_BASE}/blogs/byurl"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(
                api_url,
                params={"url": blog_url.rstrip("/")},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                blog_id = response.json().get("id")
                if blog_id:
                    logger.info(
                        f"Blogger ID (OAuth) 획득 | URL={blog_url} | "
                        f"blogger_id={blog_id}"
                    )
                    return str(blog_id)
            logger.warning(
                f"Blogger ID (OAuth) 실패 | URL={blog_url} | "
                f"status={response.status_code}"
            )
        except Exception as e:
            logger.error(
                f"Blogger ID (OAuth) 오류 | URL={blog_url} | 오류={e}"
            )
    return None
