"""리뉴얼 dry-run 검증 (단일 글) — 라이브 글/DB 미변경.

재생성까지만 수행하고 결과 요약을 출력한다. 라이브 글이나 DB는 건드리지
않으므로 안전하게 출력 양식·동작을 검증할 수 있다.

실행: docker compose exec app python -m app.scripts.renewal_dry_run <crawled_post_id>
"""
import asyncio
import json
import os
import sys


async def main(post_id: int, apply: bool = False) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.blog import Blog
    from app.models.crawled_post import CrawledPost
    from app.services.renewal.renewal_service import RenewalService

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://blogauto:blogauto123@db:5432/blogauto_v2",
    )
    engine = create_async_engine(url, echo=False)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        post = await db.get(CrawledPost, post_id)
        if not post:
            print(f"CrawledPost({post_id}) 없음")
            return
        blog = await db.get(Blog, post.blog_id)
        print(f"대상: blog={blog.name} | post={post.id} | "
              f"platform_post_id={post.platform_post_id}")
        mode = "APPLY(라이브 수정)" if apply else "DRY-RUN(미변경)"
        print(f"모드: {mode}")
        res = await RenewalService(db).renew_post(
            blog, post, dry_run=not apply,
        )
        print("RESULT: " + json.dumps(res, ensure_ascii=False))
    await engine.dispose()


if __name__ == "__main__":
    apply_mode = len(sys.argv) > 2 and sys.argv[2] == "apply"
    asyncio.run(main(int(sys.argv[1]), apply_mode))
