#!/usr/bin/env python3
"""WP 카테고리(·메뉴) 동기화 CLI — 앱 컨테이너 안에서 실행.

순서도: docs/flowcharts/wp_category_sync.md

사용법:
    python scripts/wp_sync_categories.py --blog-ids 6,7,8          # 기본 dry-run(계획만 출력)
    python scripts/wp_sync_categories.py --blog-ids 6 --apply      # 실제 생성·매핑 저장
    python scripts/wp_sync_categories.py --blog-ids 6 --apply --menu  # 메뉴까지
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _run(blog_ids: list, apply: bool, menu: bool) -> None:
    """블로그별로 sync_categories(+ensure_menu) 를 돌리고 결과를 출력한다."""
    from sqlalchemy import select

    from app.core.database import db_manager
    from app.models.blog import Blog
    from app.services.publishing.wp_category_sync import sync_categories
    from app.services.publishing.wp_menu_sync import ensure_menu, names_from_sync

    await db_manager.initialize()
    try:
        for bid in blog_ids:
            async with db_manager.get_session() as db:
                blog = (await db.execute(select(Blog).where(Blog.id == bid))).scalar_one_or_none()
                if blog is None:
                    print(f"[blog {bid}] 없음")
                    continue
                res = await sync_categories(blog, db, apply=apply)
                print(f"=== blog {bid} {blog.name} {blog.url} (apply={apply})")
                for status in ("existing", "created", "planned", "failed"):
                    for e in res[status]:
                        print(f"  {status:8} {e.get('kind')}:{e.get('id')} "
                              f"{e.get('name')} wp_id={e.get('wp_id')} {e.get('reason', '')}")
                if apply and menu:
                    m = await ensure_menu(blog, names_from_sync(res))
                    print("  menu:", json.dumps(m, ensure_ascii=False))
    finally:
        await db_manager.close()


def main() -> None:
    """인자 파싱."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blog-ids", required=True, help="쉼표 구분 블로그 ID")
    ap.add_argument("--apply", action="store_true", help="실제 생성·저장(기본 dry-run)")
    ap.add_argument("--menu", action="store_true", help="--apply 시 메뉴까지 보장")
    args = ap.parse_args()
    ids = [int(x) for x in args.blog_ids.split(",") if x.strip()]
    asyncio.run(_run(ids, args.apply, args.menu))


if __name__ == "__main__":
    main()
