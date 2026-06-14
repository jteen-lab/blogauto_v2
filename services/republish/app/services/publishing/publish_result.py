"""
발행 결과 모델

이미지 업로드, 플랫폼 발행 등 각 단계의 결과를 담는 데이터 클래스.
설계 문서: publish_module_implementation_plan.md - Phase 3.3.3
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageUploadResult:
    """이미지 업로드 결과

    Attributes:
        retryable: 실패가 일시적이어서 재시도 가치가 있으면 True.
            영구 실패(키 미설정, 파일 미존재 등)는 False.
    """

    success: bool
    platform_url: Optional[str] = None
    media_id: Optional[int] = None
    error: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    retryable: bool = True


@dataclass
class PublishResult:
    """플랫폼 발행 결과

    Attributes:
        retryable: 실패가 일시적이어서 재시도 가치가 있으면 True.
            영구 실패(인증·키 미설정, blog_id 없음, 4xx 등)는 False
            → Celery 재시도를 생략한다.
    """

    success: bool
    platform: str = ""
    published_url: Optional[str] = None
    platform_post_id: Optional[str] = None
    image_uploaded: bool = False
    image_url: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    retryable: bool = True
