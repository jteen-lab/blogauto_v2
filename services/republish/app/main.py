"""
BlogAuto V2 FastAPI 애플리케이션

Features:
- FastAPI 앱 설정
- 라우터 등록
- 미들웨어 설정
- 데이터베이스 초기화
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings
from .core.database import init_database, close_database, db_manager
from .core.logger import get_logger
from .middleware.logging_middleware import LoggingMiddleware
from .scheduler import get_scheduler, republish_job
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
from .routers.settings import router as settings_router
from .routers.modules_pages import router as modules_page_router
from .routers.flows_pages import router as flows_page_router
from .routers.autorun_pages import router as autorun_page_router

logger = get_logger("main", "app.log")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    logger.info("BlogAuto V2 애플리케이션 시작")

    # 데이터베이스 초기화
    await init_database()

    # 테이블 생성 (개발환경)
    if settings.is_development:
        await db_manager.create_tables()
        logger.info("개발환경 - 데이터베이스 테이블 생성")

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

    except Exception as e:
        logger.error(f"스케줄러 시작 실패: {e}")
        # 스케줄러 실패시에도 앱은 시작되도록 함

    yield

    # 종료 시
    try:
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
app.include_router(flows_router, prefix=settings.api_v1_prefix)
app.include_router(autorun_router, prefix=settings.api_v1_prefix)
app.include_router(dashboard_router, prefix=settings.api_v1_prefix)
app.include_router(settings_router, prefix=settings.api_v1_prefix)

# 페이지 라우터 등록
app.include_router(blogs_page_router)
app.include_router(categories_page_router)
app.include_router(republish_page_router)
# app.include_router(groups_page_router)  # 임시 비활성화
app.include_router(modules_page_router)
app.include_router(flows_page_router)
app.include_router(autorun_page_router)

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
async def dashboard_page(request: Request):
    """대시보드 페이지"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

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