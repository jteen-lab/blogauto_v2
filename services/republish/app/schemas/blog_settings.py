"""
블로그 설정 스키마 정의

블로그별 다양한 설정을 위한 Pydantic 스키마 정의.
이미지, 카테고리, 치환자, 스타일, AI 설정 등을 포함.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any


# =============================================================================
# 이미지 설정 관련 스키마
# =============================================================================

class PaddingConfig(BaseModel):
    """이미지 오버레이 패딩 설정."""

    left: int = Field(default=60, ge=0, description="왼쪽 패딩 (px)")
    right: int = Field(default=60, ge=0, description="오른쪽 패딩 (px)")
    top: int = Field(default=80, ge=0, description="상단 패딩 (px)")
    bottom: int = Field(default=80, ge=0, description="하단 패딩 (px)")


class OverlayConfig(BaseModel):
    """이미지 오버레이 설정."""

    template_image: Optional[str] = Field(
        default=None,
        description="템플릿 이미지 경로"
    )
    font_file: Optional[str] = Field(
        default=None,
        description="폰트 파일 경로"
    )
    font_size: int = Field(default=64, ge=8, le=200, description="폰트 크기")
    line_height: float = Field(
        default=1.25,
        ge=0.5,
        le=3.0,
        description="줄 높이 배율"
    )
    text_align: str = Field(
        default="center",
        pattern="^(left|center|right)$",
        description="텍스트 정렬 (left, center, right)"
    )
    vertical_align: str = Field(
        default="center",
        pattern="^(top|center|bottom)$",
        description="수직 정렬 (top, center, bottom)"
    )
    text_color: str = Field(default="#111111", description="텍스트 색상")
    stroke_enabled: bool = Field(default=False, description="외곽선 활성화")
    stroke_color: str = Field(default="#000000", description="외곽선 색상")
    stroke_width: int = Field(default=0, ge=0, le=20, description="외곽선 두께")
    shadow_enabled: bool = Field(default=False, description="그림자 활성화")
    shadow_color: str = Field(
        default="rgba(0,0,0,0.35)",
        description="그림자 색상"
    )
    shadow_blur: int = Field(default=0, ge=0, le=50, description="그림자 블러")
    shadow_offset_x: int = Field(
        default=0,
        ge=-50,
        le=50,
        description="그림자 X 오프셋"
    )
    shadow_offset_y: int = Field(
        default=0,
        ge=-50,
        le=50,
        description="그림자 Y 오프셋"
    )
    padding: PaddingConfig = Field(
        default_factory=PaddingConfig,
        description="패딩 설정"
    )


class ImageSettingsRequest(BaseModel):
    """이미지 설정 요청 스키마."""

    image_mode: str = Field(
        default="template",
        pattern="^(template|ai|both)$",
        description="이미지 모드 (template, ai, both)"
    )
    ai_image_service: str = Field(
        default="openai",
        pattern="^(openai|nanobanana)$",
        description="AI 이미지 서비스 (openai: DALL-E, nanobanana: Nano Banana)"
    )
    ai_image_model: Optional[str] = Field(
        default=None,
        description="AI 이미지 모델명 (예: dall-e-3, gpt-image-1)"
    )
    cover_source: str = Field(
        default="ai",
        pattern="^(ai|template)$",
        description="both 모드: 대표이미지 소스 (ai, template)"
    )
    section_source: str = Field(
        default="template",
        pattern="^(ai|template)$",
        description="both 모드: 섹션이미지 소스 (ai, template)"
    )
    overlay_config: OverlayConfig = Field(
        default_factory=OverlayConfig,
        description="오버레이 설정"
    )


class ImageSettingsResponse(BaseModel):
    """이미지 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    image_mode: str = Field(..., description="이미지 모드")
    ai_image_service: str = Field(
        default="openai",
        description="AI 이미지 서비스"
    )
    ai_image_model: Optional[str] = Field(
        default=None,
        description="AI 이미지 모델명"
    )
    cover_source: str = Field(
        default="ai",
        description="both 모드: 대표이미지 소스"
    )
    section_source: str = Field(
        default="template",
        description="both 모드: 섹션이미지 소스"
    )
    overlay_config: Dict[str, Any] = Field(..., description="오버레이 설정")


# =============================================================================
# 카테고리 설정 관련 스키마
# =============================================================================

class CategorySettingsRequest(BaseModel):
    """카테고리 설정 요청 스키마."""

    subcategory_ids: List[int] = Field(
        ...,
        min_length=1,
        description="선택된 서브카테고리 ID 목록"
    )


class CategorySettingsResponse(BaseModel):
    """카테고리 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    categories: List[Dict[str, Any]] = Field(
        ...,
        description="카테고리 정보 목록"
    )


# =============================================================================
# 치환자 설정 관련 스키마
# =============================================================================

class TextReplaceItem(BaseModel):
    """텍스트 치환 항목."""

    find: str = Field(..., min_length=1, description="찾을 텍스트")
    replace: str = Field(..., description="대체할 텍스트")


class LinkStyleConfig(BaseModel):
    """링크 스타일 설정."""

    default_class: str = Field(
        default="",
        description="일반 링크 CSS 클래스"
    )
    button_class: str = Field(
        default="button-link",
        description="버튼 형식 링크 CSS 클래스"
    )


class PlaceholdersConfig(BaseModel):
    """치환자 설정."""

    html_tags: Dict[str, str] = Field(
        default_factory=dict,
        description="HTML 태그 치환 설정 (예: {h1: h2})"
    )
    css_classes: Dict[str, str] = Field(
        default_factory=dict,
        description="CSS 클래스 치환 설정"
    )
    link_styles: LinkStyleConfig = Field(
        default_factory=LinkStyleConfig,
        description="링크 스타일 설정 (일반 링크, 버튼 링크)"
    )
    text_replace: List[TextReplaceItem] = Field(
        default_factory=list,
        description="텍스트 치환 목록"
    )


class PlaceholdersRequest(BaseModel):
    """치환자 설정 요청 스키마."""

    placeholders: PlaceholdersConfig = Field(
        ...,
        description="치환자 설정"
    )


class PlaceholdersResponse(BaseModel):
    """치환자 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    placeholders: Dict[str, Any] = Field(..., description="치환자 설정")


class PlaceholderPreviewRequest(BaseModel):
    """치환자 미리보기 요청 스키마."""

    content: str = Field(..., min_length=1, description="미리보기할 컨텐츠")
    placeholders: PlaceholdersConfig = Field(..., description="적용할 치환자 설정")


class PlaceholderPreviewResponse(BaseModel):
    """치환자 미리보기 응답 스키마."""

    original: str = Field(..., description="원본 컨텐츠")
    converted: str = Field(..., description="치환 적용된 컨텐츠")


# =============================================================================
# 스타일 설정 관련 스키마
# =============================================================================

class StyleConfig(BaseModel):
    """스타일 설정."""

    styles: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="CSS 스타일 설정 (선택자: {속성: 값})"
    )


class StyleSettingsRequest(BaseModel):
    """스타일 설정 요청 스키마."""

    style_config: Dict[str, Dict[str, str]] = Field(
        ...,
        description="CSS 스타일 설정"
    )


class StyleSettingsResponse(BaseModel):
    """스타일 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    style_config: Dict[str, Any] = Field(..., description="스타일 설정")
    generated_css: Optional[str] = Field(
        default=None,
        description="생성된 CSS 문자열"
    )


# =============================================================================
# AI 설정 관련 스키마
# =============================================================================

class AIServiceConfig(BaseModel):
    """AI 서비스 설정."""

    provider: Optional[str] = Field(
        default=None,
        pattern="^(openai|anthropic|google|nanobanana)?$",
        description="AI 제공자 (openai, anthropic, google, nanobanana)"
    )
    model: Optional[str] = Field(
        default=None,
        description="AI 모델명"
    )


class AIConfig(BaseModel):
    """AI 설정 통합."""

    writing_ai: AIServiceConfig = Field(
        default_factory=AIServiceConfig,
        description="글쓰기 AI 설정"
    )
    title_ai: AIServiceConfig = Field(
        default_factory=AIServiceConfig,
        description="제목 생성 AI 설정"
    )
    reference_ai: AIServiceConfig = Field(
        default_factory=AIServiceConfig,
        description="참조자료 요약 AI 설정"
    )
    image_ai: AIServiceConfig = Field(
        default_factory=AIServiceConfig,
        description="이미지 생성 AI 설정"
    )


class AISettingsRequest(BaseModel):
    """AI 설정 요청 스키마."""

    ai_config: AIConfig = Field(..., description="AI 설정")


class AISettingsResponse(BaseModel):
    """AI 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    ai_config: Dict[str, Any] = Field(..., description="AI 설정")


# =============================================================================
# 통합 설정 스키마
# =============================================================================

class BlogSettingsResponse(BaseModel):
    """블로그 전체 설정 응답 스키마."""

    blog_id: int = Field(..., description="블로그 ID")
    image_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="이미지 설정"
    )
    category_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="카테고리 설정"
    )
    placeholders: Optional[Dict[str, Any]] = Field(
        default=None,
        description="치환자 설정"
    )
    style_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="스타일 설정"
    )
    ai_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="AI 설정"
    )
