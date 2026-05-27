"""
프롬프트 빌더 페이지 라우터 (운영자 내부 도구).

특징:
- 메뉴/네비게이션에 노출 안 됨. URL 을 직접 입력해야 접근 가능.
- 인증 필요(다른 페이지와 동일하게 `get_current_user` 의존성).
- 화면에서 페르소나/독자수준/섹션패턴/시작톤을 골라 완성된
  user_prompt_template 을 실시간 미리보기 + 클립보드 복사한다.

설계 문서: docs/prompts/style_blocks.md, modules.md
"""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..models.user import User
from ..routers.auth import get_current_user
from ..services.prompt_builder import blocks_for_template

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["프롬프트 빌더 (내부)"])


@router.get("/prompt-builder", response_class=HTMLResponse)
async def prompt_builder_page(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """프롬프트 빌더 페이지.

    blocks_for_template() 의 데이터를 JSON 으로 직렬화해 템플릿에
    전달한다. 페이지의 Alpine.js 가 이 JSON 을 읽어 옵션을 렌더하고
    선택값 변경 시 클라이언트에서 즉시 본문을 조립한다.
    """
    blocks = blocks_for_template()
    return templates.TemplateResponse(
        "prompt_builder/index.html",
        {
            "request": request,
            "blocks_json": json.dumps(blocks, ensure_ascii=False),
        },
    )
