"""add category matching fields to seed_keywords and temp_titles

Revision ID: 011
Revises: 010
Create Date: 2025-01-19

카테고리 관리(Topic > SubTopic > Keyword) 연동을 위한 필드 추가
- seed_keywords: topic_id, subtopic_id, matched_keyword_id
- temp_titles: topic_id, subtopic_id, matched_keyword_id
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # seed_keywords 테이블에 카테고리 매칭 필드 추가
    op.add_column('seed_keywords', sa.Column('topic_id', sa.Integer(), nullable=True, comment='주제 ID'))
    op.add_column('seed_keywords', sa.Column('subtopic_id', sa.Integer(), nullable=True, comment='하위 주제 ID'))
    op.add_column('seed_keywords', sa.Column('matched_keyword_id', sa.Integer(), nullable=True, comment='매칭된 카테고리 키워드 ID'))

    # 외래 키 제약조건 추가 (topics, subtopics, keywords 테이블 존재 시)
    try:
        op.create_foreign_key(
            'fk_seed_keywords_topic_id', 'seed_keywords', 'topics',
            ['topic_id'], ['id'], ondelete='SET NULL'
        )
        op.create_foreign_key(
            'fk_seed_keywords_subtopic_id', 'seed_keywords', 'subtopics',
            ['subtopic_id'], ['id'], ondelete='SET NULL'
        )
        op.create_foreign_key(
            'fk_seed_keywords_matched_keyword_id', 'seed_keywords', 'keywords',
            ['matched_keyword_id'], ['id'], ondelete='SET NULL'
        )
    except Exception as e:
        print(f"Warning: Foreign key creation skipped - {e}")

    # temp_titles 테이블에 카테고리 매칭 필드 추가
    op.add_column('temp_titles', sa.Column('topic_id', sa.Integer(), nullable=True, comment='주제 ID'))
    op.add_column('temp_titles', sa.Column('subtopic_id', sa.Integer(), nullable=True, comment='하위 주제 ID'))
    op.add_column('temp_titles', sa.Column('matched_keyword_id', sa.Integer(), nullable=True, comment='매칭된 카테고리 키워드 ID'))

    # 외래 키 제약조건 추가 (topics, subtopics, keywords 테이블 존재 시)
    try:
        op.create_foreign_key(
            'fk_temp_titles_topic_id', 'temp_titles', 'topics',
            ['topic_id'], ['id'], ondelete='SET NULL'
        )
        op.create_foreign_key(
            'fk_temp_titles_subtopic_id', 'temp_titles', 'subtopics',
            ['subtopic_id'], ['id'], ondelete='SET NULL'
        )
        op.create_foreign_key(
            'fk_temp_titles_matched_keyword_id', 'temp_titles', 'keywords',
            ['matched_keyword_id'], ['id'], ondelete='SET NULL'
        )
    except Exception as e:
        print(f"Warning: Foreign key creation skipped - {e}")

    # 인덱스 추가 (조회 성능 향상)
    op.create_index('ix_seed_keywords_topic_id', 'seed_keywords', ['topic_id'])
    op.create_index('ix_seed_keywords_subtopic_id', 'seed_keywords', ['subtopic_id'])
    op.create_index('ix_temp_titles_topic_id', 'temp_titles', ['topic_id'])
    op.create_index('ix_temp_titles_subtopic_id', 'temp_titles', ['subtopic_id'])


def downgrade() -> None:
    # 인덱스 삭제
    op.drop_index('ix_temp_titles_subtopic_id', table_name='temp_titles')
    op.drop_index('ix_temp_titles_topic_id', table_name='temp_titles')
    op.drop_index('ix_seed_keywords_subtopic_id', table_name='seed_keywords')
    op.drop_index('ix_seed_keywords_topic_id', table_name='seed_keywords')

    # 외래 키 제약조건 삭제
    try:
        op.drop_constraint('fk_temp_titles_matched_keyword_id', 'temp_titles', type_='foreignkey')
        op.drop_constraint('fk_temp_titles_subtopic_id', 'temp_titles', type_='foreignkey')
        op.drop_constraint('fk_temp_titles_topic_id', 'temp_titles', type_='foreignkey')
        op.drop_constraint('fk_seed_keywords_matched_keyword_id', 'seed_keywords', type_='foreignkey')
        op.drop_constraint('fk_seed_keywords_subtopic_id', 'seed_keywords', type_='foreignkey')
        op.drop_constraint('fk_seed_keywords_topic_id', 'seed_keywords', type_='foreignkey')
    except Exception:
        pass

    # 컬럼 삭제
    op.drop_column('temp_titles', 'matched_keyword_id')
    op.drop_column('temp_titles', 'subtopic_id')
    op.drop_column('temp_titles', 'topic_id')
    op.drop_column('seed_keywords', 'matched_keyword_id')
    op.drop_column('seed_keywords', 'subtopic_id')
    op.drop_column('seed_keywords', 'topic_id')
