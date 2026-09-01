"""발행·생성 순서와 당일 카운트 (2026-09-01).

세 가지를 고쳤다.

1. `_today_generated_count` 가 24시간 롤링 창을 썼다. 어제 만든 글이 오늘
   몫으로 잡혀, 상한이 1인 블로그는 이틀에 한 번만 생성됐다
   (굿팁꿀팁 09-01 "오늘 2개" ← 08-31 의 2건).
2. 오토런 첫 등록에서 생성과 발행이 모두 '3초 뒤' 로 잡혀 동시에 돌았다.
   발행이 아직 만들어지지도 않은 글을 찾다 건너뛰었다.
3. 발행할 글이 없으면 10분마다 되물었다. 생성 전에는 결과가 같다.

조사: docs/plans/publish_skip_investigation.md
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytz

ROOT = Path(__file__).resolve().parents[2]
KST = pytz.timezone("Asia/Seoul")


# ── 1. 당일 기준 ─────────────────────────────────────────
def test_today_count_uses_calendar_day_not_rolling_window() -> None:
    """24시간 창이면 어제 것이 오늘로 잡힌다."""
    src = (ROOT / "app/services/generation/flow_generate_executor.py").read_text(
        encoding="utf-8")
    start = src.index("async def _today_generated_count")
    end = src.index("def _filter_categories_for_blog")
    body = src[start:end]

    assert "timedelta(hours=24)" not in body, "24시간 롤링 창이 남아 있다"
    assert "Asia/Seoul" in body, "KST 자정 기준이어야 한다"
    assert "time.min" in body
    assert "< end" in body, "당일 끝도 막아야 다음 날 것이 안 섞인다"


def test_day_boundary_math() -> None:
    """08-31 22:04 생성분은 09-01 판정에 잡히면 안 된다."""
    now = KST.localize(datetime(2026, 9, 1, 9, 0))
    start = KST.localize(datetime.combine(now.date(), datetime.min.time()))
    end = start + timedelta(days=1)

    yesterday_late = KST.localize(datetime(2026, 8, 31, 22, 4))
    today_noon = KST.localize(datetime(2026, 9, 1, 12, 59))

    assert not (start <= yesterday_late < end), "어제 것이 오늘로 잡힌다"
    assert start <= today_noon < end

    # 옛 방식이었다면 잡혔다는 것도 함께 보인다
    rolling = now - timedelta(hours=24)
    assert yesterday_late >= rolling, "옛 24시간 창은 어제 것을 잡았다"


def test_skip_message_shows_the_basis_and_gp_override() -> None:
    """'제한' 이라고만 하면 GP 설정이 무시된 것처럼 보인다."""
    src = (ROOT / "app/services/generation/flow_generate_executor.py").read_text(
        encoding="utf-8")
    assert "오늘(00시 기준)" in src
    assert "성장 프로파일" in src and "색인 되먹임으로" in src


# ── 2. 즉시 실행 순서 ────────────────────────────────────
def test_generate_runs_before_publish_on_first_registration() -> None:
    """둘 다 3초 뒤면 발행이 빈 재고를 본다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    delays = FlowScheduler.IMMEDIATE_DELAYS
    assert delays["generate"] < delays["publish"], \
        "생성이 발행보다 먼저 시작해야 한다"
    assert delays["publish"] - delays["generate"] >= 60, \
        "한 편 만드는 데 20~40초가 걸린다. 여유가 필요하다"
    assert delays["republish"] >= delays["publish"]


def test_immediate_delay_has_a_default() -> None:
    """새 액션 타입이 늘어도 죽지 않아야 한다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    assert "IMMEDIATE_DELAYS.get(action_type, 3)" in src
    assert "keyword" in FlowScheduler.IMMEDIATE_DELAYS


# ── 3. 재고 선확인 ───────────────────────────────────────
def test_inventory_checked_before_heavy_setup() -> None:
    """발행할 글이 없으면 GP 컨텍스트·파이프라인을 만들 이유가 없다."""
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    start = src.index("async def _execute_publish_action")
    end = src.index("async def _execute_republish_action")
    body = src[start:end]

    pre_check = body.index("get_post_for_publish")
    gp_build = body.index("GrowthProfileResolver.build_execution_context")
    assert pre_check < gp_build, "무거운 준비가 재고 확인보다 먼저다"


def test_skip_reason_is_recorded() -> None:
    """'발행 가능 글 없음' 만으로는 카테고리 불일치인지 알 수 없다.

    굿팁꿀팁이 30번 스킵하는 동안 진짜 이유가 한 번도 안 남았다.
    """
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    start = src.index("async def _execute_publish_action")
    end = src.index("async def _execute_republish_action")
    body = src[start:end]
    assert "describe_publish_block" in body[:body.index("gp_context = None")]


# ── 4. 생성 대기 스케줄 ──────────────────────────────────
@pytest.mark.asyncio
async def test_waits_for_next_generation_not_ten_minute_poll() -> None:
    """생성 전에는 되물어도 결과가 같다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    sched = FlowScheduler.__new__(FlowScheduler)
    sched._get_gp_interval = lambda gp, blogs, action: 240   # 발행 주기 4시간
    gen_next = datetime.now(KST) + timedelta(minutes=30)
    sched._get_execution_state = AsyncMock(
        return_value=SimpleNamespace(next_execution_at=gen_next))

    run_time = await sched._next_publish_attempt(
        SimpleNamespace(id=1), "publish", {"stages": []}, [], db=object())

    # 다음 생성 + 여유
    expected = gen_next + timedelta(
        seconds=FlowScheduler.PUBLISH_AFTER_GENERATE_SEC)
    assert abs((run_time - expected).total_seconds()) < 2


@pytest.mark.asyncio
async def test_never_waits_longer_than_publish_interval() -> None:
    """수동 생성 등 다른 경로로 글이 생길 수 있다. 손 놓으면 안 된다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    sched = FlowScheduler.__new__(FlowScheduler)
    sched._get_gp_interval = lambda gp, blogs, action: 60    # 발행 주기 1시간
    far = datetime.now(KST) + timedelta(hours=10)            # 생성은 10시간 뒤
    sched._get_execution_state = AsyncMock(
        return_value=SimpleNamespace(next_execution_at=far))

    run_time = await sched._next_publish_attempt(
        SimpleNamespace(id=1), "publish", {"stages": []}, [], db=object())

    assert run_time < datetime.now(KST) + timedelta(minutes=61), \
        "발행 주기보다 오래 기다리면 안 된다"


@pytest.mark.asyncio
async def test_falls_back_when_no_generate_action() -> None:
    """생성 모듈이 없는 플로우도 있다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    sched = FlowScheduler.__new__(FlowScheduler)
    sched._get_gp_interval = lambda gp, blogs, action: 90
    sched._get_execution_state = AsyncMock(return_value=None)

    run_time = await sched._next_publish_attempt(
        SimpleNamespace(id=1), "publish", {"stages": []}, [], db=object())

    delta = (run_time - datetime.now(KST)).total_seconds() / 60
    assert 85 < delta < 95, "발행 주기를 써야 한다"


@pytest.mark.asyncio
async def test_overdue_generation_rechecks_soon() -> None:
    """생성 예정이 이미 지났으면(밀렸으면) 짧게 다시 본다."""
    from app.scheduler.flow_scheduler import FlowScheduler

    sched = FlowScheduler.__new__(FlowScheduler)
    sched._get_gp_interval = lambda gp, blogs, action: 240
    past = datetime.now(KST) - timedelta(hours=3)
    sched._get_execution_state = AsyncMock(
        return_value=SimpleNamespace(next_execution_at=past))

    run_time = await sched._next_publish_attempt(
        SimpleNamespace(id=1), "publish", {"stages": []}, [], db=object())

    delta = (run_time - datetime.now(KST)).total_seconds() / 60
    assert 3 < delta < 7


def test_await_generation_records_execution() -> None:
    """카운터를 안 올리면 '최초 실행' 상태를 못 벗어난다.

    옛 skip_interval 경로가 그래서 10분마다 무한 재시도했다.
    """
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    start = src.index('if result.get("await_generation"):')
    end = src.index('elif result.get("skip_interval"):')
    body = src[start:end]
    assert "record_execution(True)" in body
    assert "_next_publish_attempt" in body


# ── 5. Celery 위임 발행이 실패로 집계되던 문제 ────────────
def test_celery_dispatch_is_not_counted_as_failure() -> None:
    """디스패치 성공을 실패로 세면 연속 실패가 쌓인다.

    인포노트가 08-30 정상 발행하고도 consecutive_failures=2 였다.
    Celery 결과 dict 는 crawled_post 도 skipped 도 없어서 else 로 떨어졌다.
    """
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    start = src.index("async def _execute_publish_action")
    end = src.index("async def _execute_republish_action")
    body = src[start:end]

    tail = body[body.index('elif pub_result.get("skipped"):'):]
    branch = tail[:tail.index("blog_duration = int(")]
    # skipped 다음, else 앞에 success 가지가 있어야 한다
    assert 'elif pub_result.get("success"):' in branch
    assert branch.index('elif pub_result.get("success"):') < branch.index("else:")


def test_publisher_always_marks_direct_results() -> None:
    """직접 발행 경로는 위 가지로 새지 않는다.

    publish_for_blog 는 skipped 이거나 crawled_post 를 달고 온다.
    이 성질이 깨지면 실패한 발행이 성공으로 집계된다.
    """
    src = (ROOT / "app/services/generation/publisher.py").read_text(
        encoding="utf-8")
    start = src.index("async def publish_for_blog")
    end = src.index("async def complete_publish")
    returns = re.findall(r"return \{(.*?)\n\s*\}", src[start:end], re.S)
    assert len(returns) == 3
    for r in returns:
        assert '"skipped": True' in r or '"crawled_post"' in r, r[:80]


def test_first_run_recheck_no_longer_polls_every_ten_minutes() -> None:
    """최초 실행 재고 대기도 생성 시각을 본다."""
    src = (ROOT / "app/scheduler/flow_scheduler.py").read_text(encoding="utf-8")
    start = src.index('elif result.get("skip_interval"):')
    end = src.index('elif (\n                        "일일"')
    body = src[start:end]
    assert "MIN_CHECK_INTERVAL" not in body, "10분 고정 폴링이 남아 있다"
    assert "_next_publish_attempt" in body
    assert "record_execution" not in body, "간격 미소비 성질을 지켜야 한다"
