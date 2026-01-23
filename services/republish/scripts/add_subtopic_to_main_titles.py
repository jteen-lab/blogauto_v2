"""
main_titles 테이블에 topic_id, subtopic_id 컬럼 추가 마이그레이션

실행 방법:
    docker exec -it republish_app python scripts/add_subtopic_to_main_titles.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


async def migrate():
    """main_titles 테이블에 topic_id, subtopic_id 컬럼 추가"""
    async with engine.begin() as conn:
        # 컬럼 존재 여부 확인
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'main_titles' AND column_name = 'topic_id'
        """))
        topic_exists = result.fetchone() is not None

        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'main_titles' AND column_name = 'subtopic_id'
        """))
        subtopic_exists = result.fetchone() is not None

        if topic_exists and subtopic_exists:
            print("이미 topic_id, subtopic_id 컬럼이 존재합니다.")
            return

        # topic_id 컬럼 추가
        if not topic_exists:
            print("topic_id 컬럼 추가 중...")
            await conn.execute(text("""
                ALTER TABLE main_titles
                ADD COLUMN topic_id INTEGER REFERENCES topics(id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_main_titles_topic_id ON main_titles(topic_id)
            """))
            print("topic_id 컬럼 추가 완료")

        # subtopic_id 컬럼 추가
        if not subtopic_exists:
            print("subtopic_id 컬럼 추가 중...")
            await conn.execute(text("""
                ALTER TABLE main_titles
                ADD COLUMN subtopic_id INTEGER REFERENCES subtopics(id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_main_titles_subtopic_id ON main_titles(subtopic_id)
            """))
            print("subtopic_id 컬럼 추가 완료")

        print("마이그레이션 완료!")


if __name__ == "__main__":
    asyncio.run(migrate())
