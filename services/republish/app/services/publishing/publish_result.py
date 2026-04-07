"""
발행 결과 모델

이미지 업로드, 플랫폼 발행 등 각 단계의 결과를 담는 데이터 클래스.
설계 문서: publish_module_implementation_plan.md - Phase 3.3.3
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageUploadResult:
    """이미지 업로드 결과"""

    success: bool
    platform_url: Optional[str] = None
    media_id: Optional[int] = None
    error: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class PublishResult:
    """플랫폼 발행 결과"""

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
