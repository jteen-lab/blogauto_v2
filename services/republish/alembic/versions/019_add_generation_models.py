"""Add generation module models

Revision ID: 019
Revises: 018
Create Date: 2026-02-09

Phase G-1: 생성 모듈 기반 인프라
- generation_histories: 생성 이력 메타데이터
- blog_growth_settings: 블로그 성장 단계별 설정
- crawled_posts.generation_history_id: 생성 이력 FK 추가
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. generation_histories 테이블 생성
    op.create_table(
        'generation_histories',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        # 관계 FK
        sa.Column(
            'blog_id',
            sa.Integer(),
            sa.ForeignKey('blogs.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'source_title_id',
            sa.Integer(),
            sa.ForeignKey('main_titles.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
        ),
        sa.Column(
            'prompt_module_id',
            sa.Integer(),
            sa.ForeignKey('modules.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
        ),
        sa.Column(
            'crawling_post_id',
            sa.Integer(),
            sa.ForeignKey('crawled_posts.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
        ),
        # 생성 결과
        sa.Column(
            'recombined_title',
            sa.String(500),
            nullable=True,
            comment='재조합된 제목',
        ),
        # 사용된 AI 모델
        sa.Column(
            'ai_model_title',
            sa.String(100),
            nullable=True,
            comment='제목 재조합에 사용된 AI 모델',
        ),
        sa.Column(
            'ai_model_content',
            sa.String(100),
            nullable=True,
            comment='글 생성에 사용된 AI 모델',
        ),
        sa.Column(
            'ai_model_image',
            sa.String(100),
            nullable=True,
            comment='이미지 생성에 사용된 AI 모델',
        ),
        # 통계
        sa.Column(
            'reference_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='수집된 참조자료 수',
        ),
        sa.Column(
            'generation_time_seconds',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='총 생성 소요 시간(초)',
        ),
        sa.Column(
            'content_length',
            sa.Integer(),
            nullable=False,
            server_default='0',
            comment='생성된 글 길이',
        ),
        # 버전 관리
        sa.Column(
            'version',
            sa.Integer(),
            nullable=False,
            server_default='1',
            comment='같은 제목의 몇 번째 버전',
        ),
        # 타임스탬프
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # generation_histories 복합 인덱스
    op.create_index(
        'ix_gen_history_blog_created',
        'generation_histories',
        ['blog_id', 'created_at'],
    )

    # 2. blog_growth_settings 테이블 생성
    op.create_table(
        'blog_growth_settings',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column(
            'blog_id',
            sa.Integer(),
            sa.ForeignKey('blogs.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
            index=True,
        ),
        # 급성장기 설정
        sa.Column(
            'rapid_growth_threshold',
            sa.Integer(),
            nullable=False,
            server_default='50',
            comment='급성장기 기준 (이 수 이하)',
        ),
        sa.Column(
            'rapid_growth_inventory',
            sa.Integer(),
            nullable=False,
            server_default='10',
            comment='급성장기 재고 기준값',
        ),
        # 성장기 설정
        sa.Column(
            'growth_threshold',
            sa.Integer(),
            nullable=False,
            server_default='150',
            comment='성장기 기준 (이 수 이하)',
        ),
        sa.Column(
            'growth_inventory',
            sa.Integer(),
            nullable=False,
            server_default='5',
            comment='성장기 재고 기준값',
        ),
        # 안정기 설정
        sa.Column(
            'stable_inventory',
            sa.Integer(),
            nullable=False,
            server_default='2',
            comment='안정기 재고 기준값',
        ),
        # 타임스탬프
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # 3. crawled_posts에 generation_history_id 컬럼 추가
    op.add_column(
        'crawled_posts',
        sa.Column(
            'generation_history_id',
            sa.Integer(),
            sa.ForeignKey('generation_histories.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
            comment='생성 이력 FK (자동 생성된 글만)',
        ),
    )


def downgrade() -> None:
    # 3. crawled_posts에서 generation_history_id 컬럼 제거
    op.drop_column('crawled_posts', 'generation_history_id')

    # 2. blog_growth_settings 테이블 삭제
    op.drop_table('blog_growth_settings')

    # 1. generation_histories 테이블 삭제
    op.drop_index(
        'ix_gen_history_blog_created',
        table_name='generation_histories',
    )
    op.drop_table('generation_histories')
