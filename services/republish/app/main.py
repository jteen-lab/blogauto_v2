"""
BlogAuto V2 FastAPI 애플리케이션

Features:
- FastAPI 앱 설정
- 라우터 등록
- 미들웨어 설정
- 데이터베이스 초기화
"""
import json

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings, validate_env_required
from .core.database import get_db_session, init_database, close_database, db_manager
from .core.logger import get_logger
from .middleware.logging_middleware import LoggingMiddleware
from .scheduler import get_scheduler, republish_job, setup_flow_scheduler, shutdown_flow_scheduler
from .scheduler.search_visibility_job import (  # 검색 노출 S2/S6/S6-N
    index_check_job, naver_index_check_job, sitemap_check_job,
)
from .routers.auth import router as auth_router
from .routers.blogs import router as blogs_router, page_router as blogs_page_router
from .routers.categories import router as categories_router, page_router as categories_page_router
from .routers.republish import router as republish_router, page_router as republish_page_router
# from .routers.groups import router as groups_router, page_router as groups_page_router  # 임시 비활성화
# from .routers.blogger_slots import router as blogger_slots_router  # 임시 비활성화
from .routers.module_types import router as module_types_router
from .routers.modules import router as modules_router
from .routers.flows import router as flows_router
from .routers.autorun import router as autorun_router
from .routers.dashboard import router as dashboard_router
from .routers.dashboard_celery import router as dashboard_celery_router
from .routers.settings import router as settings_router, naver_search_router, naver_ads_router, google_trends_router, naver_datalab_router, google_keyword_planner_router, system_settings_router
from .routers.modules_pages import router as modules_page_router
from .routers.flows_pages import router as flows_page_router
from .routers.autorun_pages import router as autorun_page_router
from .routers.engine import router as engine_router
from .routers.flows_execute import router as flows_execute_router
from .routers.collection_pages import router as collection_page_router
from .routers.data_keywords import router as data_keywords_router
from .routers.data_titles import router as data_titles_router
from .routers.data_filters import router as data_filters_router
from .routers.data_urls import router as data_urls_router
from .routers.titles import router as titles_router  # Phase C: MainTitle API
from .routers.title_groups import router as title_groups_router  # Phase C: TitleGroup API
from .routers.title_transfer import router as title_transfer_router  # Phase D: Title Transfer API
from .routers.blog_settings import router as blog_settings_router  # 블로그 설정 API
from .routers.blog_settings_seo import router as blog_settings_seo_router  # 블로그 SEO 설정 API
from .routers.blog_settings_renewal import router as blog_settings_renewal_router  # 블로그 재발행 리뉴얼 설정 API
from .routers.blog_settings_adsense import router as blog_settings_adsense_router  # 블로그 애드센스 승인 지원 설정 API
from .routers.contact_submissions import router as contact_submissions_router  # 문의 수신함 API (F10)
from .routers.search_visibility import router as search_visibility_router  # 검색 노출 3종 API (S1/S2/S6)
from .routers.ai_api_keys import router as ai_api_keys_router  # AI API 키 다계정 관리
from .routers.ai_models import router as ai_models_router  # AI 모델 카탈로그
from .routers.reference_collection import router as reference_collection_router  # 참조자료 수집
from .api.growth_profile import router as growth_profile_router  # Growth Profile API
from .routers.generation_test import router as generation_test_router  # Phase D: 파이프라인 테스트
from .routers.generation_content import router as generation_content_router  # 생성 콘텐츠 조회/삭제
from .routers.generation_pages import router as generation_page_router  # 생성 이력 페이지
from .routers.prompt_builder_pages import router as prompt_builder_page_router  # 프롬프트 빌더 (메뉴 미노출, URL 직접 접근)
from .routers.prompt_blocks import router as prompt_blocks_router  # 프롬프트 빌더 옵션 CRUD
from .routers.task_status import router as task_status_router  # Phase 3: Celery task 상태 폴링
from .routers.dashboard_trends import router as dashboard_trends_router  # 대시보드 v2 트렌드 API
from .routers.dashboard_logs import router as dashboard_logs_router  # 통합 동작로그 API

logger = get_logger("main", "app.log")


async def seed_module_types():
    """누락된 모듈 타입을 자동으로 추가하고, 지정된 리네임만 적용한다.

    기존 행의 name/icon은 사용자가 바꿨을 수 있으므로 일괄 덮어쓰지 않는다.
    `_MODULE_TYPE_RENAMES`에 등록된 (구 이름/구 아이콘)과 정확히 일치할 때만
    새 값으로 갱신한다. display_order는 사용자 정렬 보존을 위해 건드리지 않는다.
    """
    from sqlalchemy import select
    from .models.module_type import ModuleType

    # {code: (구 이름, 새 이름, 구 아이콘, 새 아이콘)} — 값이 구 값일 때만 갱신
    _MODULE_TYPE_RENAMES = {
        "contact_form": ("문의폼", "애드센스 필수구성", "📨", "📋"),
    }

    try:
        async with db_manager.get_session() as session:
            # 기본 모듈 타입 목록
            default_types = ModuleType.get_default_types()

            # 기존 모듈 타입 조회(코드→행)
            result = await session.execute(select(ModuleType))
            existing = {mt.code: mt for mt in result.scalars().all()}

            # 누락 추가
            added_count = 0
            for type_data in default_types:
                code = type_data["code"]
                if code in existing:
                    continue
                session.add(ModuleType(
                    code=code,
                    name=type_data["name"],
                    icon=type_data.get("icon"),
                    display_order=type_data.get("display_order", 0),
                ))
                added_count += 1
                logger.info(f"모듈 타입 추가: {code} ({type_data['name']})")

            # 지정 리네임(구 값과 일치할 때만)
            renamed_count = 0
            for code, (old_name, new_name, old_icon, new_icon) in _MODULE_TYPE_RENAMES.items():
                mt = existing.get(code)
                if not mt:
                    continue
                changed = False
                if mt.name == old_name:
                    mt.name = new_name
                    changed = True
                if mt.icon == old_icon:
                    mt.icon = new_icon
                    changed = True
                if changed:
                    renamed_count += 1
                    logger.info(f"모듈 타입 리네임: {code} → {mt.name} {mt.icon}")

            if added_count or renamed_count:
                await session.commit()
                logger.info(f"모듈 타입 추가 {added_count}개 · 리네임 {renamed_count}개 완료")
            else:
                logger.info("모든 모듈 타입이 최신 상태입니다")

    except Exception as e:
        logger.error(f"모듈 타입 초기화 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    logger.info("BlogAuto V2 애플리케이션 시작")

    # 필수 환경변수 검증
    missing_vars = validate_env_required()
    if missing_vars:
        logger.warning(
            f"[ENV] 필수 환경변수 누락: {', '.join(missing_vars)} | "
            f".env 파일을 확인하세요 (.env.required 참조)"
        )

    # Celery 기능 플래그 상태 로깅
    logger.info(
        f"[CELERY] 기능 플래그 상태 | "
        f"generation={settings.use_celery_generation} | "
        f"publish={settings.use_celery_publish} | "
        f"utility={settings.use_celery_utility}"
    )

    # 노드 모듈 등록
    from app.modules import register_all_modules
    register_all_modules()
    logger.info("노드 모듈 등록 완료")

    # 데이터베이스 초기화
    await init_database()

    # 테이블 생성 (개발환경)
    if settings.is_development:
        await db_manager.create_tables()
        logger.info("개발환경 - 데이터베이스 테이블 생성")

    # 모듈 타입 초기화 (누락된 타입 자동 추가)
    await seed_module_types()

    # 스케줄러 시작
    try:
        scheduler = await get_scheduler()
        await scheduler.start()
        logger.info("스케줄러 시작됨")

        # 재발행 Job 등록 (1분마다 실행)
        scheduler.add_job(
            republish_job,
            "interval",
            minutes=1,
            id="republish_job",
            name="재발행 작업",
            replace_existing=True
        )
        logger.info("재발행 Job 등록됨")

        # 검색 노출 점검 Job (S2 사이트맵 30분, S6 색인 6시간)
        scheduler.add_job(
            sitemap_check_job,
            "interval",
            minutes=30,
            id="sitemap_check_job",
            name="사이트맵 신선도 점검",
            replace_existing=True,
        )
        scheduler.add_job(
            index_check_job,
            "interval",
            hours=6,
            id="index_check_job",
            name="색인 상태 점검",
            replace_existing=True,
        )
        scheduler.add_job(
            naver_index_check_job,
            "interval",
            hours=8,
            id="naver_index_check_job",
            name="네이버 색인 점검",
            replace_existing=True,
        )
        logger.info(
            "검색 노출 점검 Job 등록됨 (사이트맵 30분 / 구글색인 6시간 / 네이버 8시간)"
        )

        # 플로우 스케줄러 시작
        await setup_flow_scheduler()
        logger.info("플로우 스케줄러 시작됨")

    except Exception as e:
        logger.error(f"스케줄러 시작 실패: {e}")
        # 스케줄러 실패시에도 앱은 시작되도록 함

    yield

    # 종료 시
    try:
        # 플로우 스케줄러 종료
        await shutdown_flow_scheduler()
        logger.info("플로우 스케줄러 종료됨")

        scheduler = await get_scheduler()
        await scheduler.shutdown()
        logger.info("스케줄러 종료됨")
    except Exception as e:
        logger.error(f"스케줄러 종료 실패: {e}")

    await close_database()
    logger.info("BlogAuto V2 애플리케이션 종료")

# FastAPI 앱 생성
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="BlogAuto V2 - 블로그 자동화 시스템",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None
)

# 템플릿 설정
templates = Jinja2Templates(directory="app/templates")

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# 커스텀 미들웨어 추가
app.add_middleware(LoggingMiddleware)

# API 라우터 등록
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(blogs_router, prefix=settings.api_v1_prefix)
app.include_router(categories_router, prefix=settings.api_v1_prefix)
app.include_router(republish_router, prefix=settings.api_v1_prefix)
# app.include_router(groups_router, prefix=settings.api_v1_prefix)  # 임시 비활성화
# app.include_router(blogger_slots_router, prefix=settings.api_v1_prefix)  # 임시 비활성화
app.include_router(module_types_router, prefix=settings.api_v1_prefix)
app.include_router(modules_router, prefix=settings.api_v1_prefix)
app.include_router(flows_execute_router)  # 먼저 등록 (더 구체적인 경로)
app.include_router(flows_router, prefix=settings.api_v1_prefix)
app.include_router(autorun_router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_celery_router, prefix=settings.api_v1_prefix)
app.include_router(settings_router, prefix=settings.api_v1_prefix)
app.include_router(naver_search_router, prefix=settings.api_v1_prefix)
app.include_router(naver_ads_router, prefix=settings.api_v1_prefix)
app.include_router(google_trends_router, prefix=settings.api_v1_prefix)
app.include_router(naver_datalab_router, prefix=settings.api_v1_prefix)
app.include_router(google_keyword_planner_router, prefix=settings.api_v1_prefix)
app.include_router(system_settings_router, prefix=settings.api_v1_prefix)
app.include_router(task_status_router, prefix=settings.api_v1_prefix)  # Phase 3: Celery task 상태
app.include_router(engine_router, prefix=settings.api_v1_prefix)
app.include_router(data_keywords_router, prefix=settings.api_v1_prefix)
app.include_router(data_titles_router, prefix=settings.api_v1_prefix)
app.include_router(data_filters_router, prefix=settings.api_v1_prefix)
app.include_router(data_urls_router, prefix=settings.api_v1_prefix)
app.include_router(titles_router, prefix=settings.api_v1_prefix)  # Phase C: MainTitle
app.include_router(title_groups_router, prefix=settings.api_v1_prefix)  # Phase C: TitleGroup
app.include_router(title_transfer_router, prefix=settings.api_v1_prefix)  # Phase D: Title Transfer
app.include_router(blog_settings_router, prefix=settings.api_v1_prefix)  # 블로그 설정
app.include_router(blog_settings_seo_router, prefix=settings.api_v1_prefix)  # 블로그 SEO 설정
app.include_router(blog_settings_renewal_router, prefix=settings.api_v1_prefix)  # 블로그 재발행 리뉴얼 설정
app.include_router(blog_settings_adsense_router, prefix=settings.api_v1_prefix)  # 블로그 애드센스 승인 지원 설정
app.include_router(contact_submissions_router, prefix=settings.api_v1_prefix)  # 문의 수신함 (F10)
app.include_router(search_visibility_router, prefix=settings.api_v1_prefix)  # 검색 노출 3종 (S1/S2/S6)
app.include_router(ai_api_keys_router)  # AI API 키 다계정 관리 (prefix 포함)
app.include_router(ai_models_router)  # AI 모델 카탈로그 (prefix 포함)
app.include_router(reference_collection_router, prefix=settings.api_v1_prefix)  # 참조자료 수집
app.include_router(growth_profile_router, prefix=settings.api_v1_prefix)  # Growth Profile
app.include_router(generation_test_router, prefix=settings.api_v1_prefix)  # Phase D: 파이프라인 테스트
app.include_router(generation_content_router, prefix=settings.api_v1_prefix)  # 생성 콘텐츠 조회/삭제
app.include_router(dashboard_trends_router, prefix=settings.api_v1_prefix)  # 대시보드 v2 트렌드
app.include_router(dashboard_logs_router, prefix=settings.api_v1_prefix)  # 통합 동작로그

# 페이지 라우터 등록
app.include_router(blogs_page_router)
app.include_router(categories_page_router)
app.include_router(republish_page_router)
# app.include_router(groups_page_router)  # 임시 비활성화
app.include_router(modules_page_router)
app.include_router(flows_page_router)
app.include_router(autorun_page_router)
app.include_router(collection_page_router)
app.include_router(generation_page_router)  # 생성 이력 페이지
app.include_router(prompt_builder_page_router)  # 프롬프트 빌더 (메뉴 미노출)
app.include_router(prompt_blocks_router)  # 프롬프트 빌더 옵션 CRUD API

# 정적 파일 서빙 (개발환경)
if settings.is_development:
    try:
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
    except Exception:
        pass  # static 디렉토리가 없으면 무시

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    """메인 페이지 - 로그인 페이지로 리다이렉트"""
    return RedirectResponse(url="/login", status_code=302)

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """로그인 페이지"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """대시보드 페이지 (SSR 초기 데이터 포함)."""
    initial_data = await _get_dashboard_initial(db)
    return templates.TemplateResponse(
        "dashboard/dashboard_v2.html",
        {"request": request, "initial_data": json.dumps(initial_data, default=str)},
    )


async def _get_dashboard_initial(db: AsyncSession) -> dict:
    """대시보드 초기 데이터를 수집합니다.

    Args:
        db: 비동기 DB 세션

    Returns:
        dict: summary 키를 포함하는 초기 데이터 딕셔너리
    """
    try:
        from .routers.dashboard import get_dashboard_summary
        summary = await get_dashboard_summary(db)
        return {"summary": summary}
    except Exception:
        logger.warning("[DASHBOARD] SSR 초기 데이터 수집 실패")
        return {"summary": {}}

@app.get("/health", include_in_schema=False)
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment
    }

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404 페이지"""
    logger.warning(f"404 에러 | 경로={request.url.path} | IP={request.client.host}")
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 404,
            "message": "페이지를 찾을 수 없습니다"
        },
        status_code=404
    )

@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc):
    """500 에러 페이지"""
    logger.error(f"500 에러 | 경로={request.url.path} | IP={request.client.host} | 오류={str(exc)}")
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status_code": 500,
            "message": "서버 내부 오류가 발생했습니다"
        },
        status_code=500
    )

if __name__ == "__main__":
    import uvicorn

    logger.info(f"서버 시작 | 호스트={settings.host} | 포트={settings.port}")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload and settings.is_development,
        log_level=settings.log_level.lower()
    )