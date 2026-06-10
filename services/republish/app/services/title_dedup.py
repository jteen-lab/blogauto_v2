"""제목 중복 판정 공통 유틸.

수집/등록 시 임시(TempTitle)와 정식(MainTitle) 제목 모두를 대상으로
중복을 판정한다.

기존에는 각 수집 경로가 TempTitle 만 비교해, 정식제목과 완전히 같은
임시제목이 유입되는 결함이 있었다(요구사항: "이미 수집된 제목과 중복이면
수집하지 않는다 — 임시·정식 모두 포함"). 본 유틸로 판정 기준을 일원화한다.

정규화는 ``strip().lower()`` (대소문자 무시) 기준이며, DB 측도 ``lower()`` 로
비교해 일관성을 맞춘다.
"""
from __future__ import annotations

from typing import Iterable, Set

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.title import TempTitle, MainTitle


def normalize_title_key(title: str) -> str:
    """중복 비교용 정규화 키 (앞뒤 공백 제거 + 소문자)."""
    return (title or "").strip().lower()


async def title_exists(db: AsyncSession, title: str) -> bool:
    """제목이 임시(TempTitle) 또는 정식(MainTitle)에 이미 존재하는지.

    대소문자를 무시하고 비교한다. 단건 수집 경로에서 사용한다.

    Args:
        db: 비동기 세션
        title: 검사할 제목

    Returns:
        임시 또는 정식에 같은 제목이 있으면 True
    """
    key = normalize_title_key(title)
    if not key:
        return False

    temp = await db.execute(
        select(TempTitle.id)
        .where(func.lower(TempTitle.title) == key)
        .limit(1)
    )
    if temp.scalar_one_or_none() is not None:
        return True

    main = await db.execute(
        select(MainTitle.id)
        .where(func.lower(MainTitle.title) == key)
        .limit(1)
    )
    return main.scalar_one_or_none() is not None


async def existing_title_keys(
    db: AsyncSession, titles: Iterable[str]
) -> Set[str]:
    """주어진 제목들 중 임시 또는 정식에 이미 존재하는 것의 정규화 키 집합.

    배치 수집에서 한 번의 조회로 기존 제목을 걸러내는 데 사용한다.

    Args:
        db: 비동기 세션
        titles: 검사할 제목 목록

    Returns:
        이미 존재하는 제목의 정규화 키(소문자) 집합
    """
    keys = {normalize_title_key(t) for t in titles}
    keys.discard("")
    if not keys:
        return set()

    key_list = list(keys)
    found: Set[str] = set()

    temp_rows = await db.execute(
        select(func.lower(TempTitle.title)).where(
            func.lower(TempTitle.title).in_(key_list)
        )
    )
    found.update(row[0] for row in temp_rows.all())

    main_rows = await db.execute(
        select(func.lower(MainTitle.title)).where(
            func.lower(MainTitle.title).in_(key_list)
        )
    )
    found.update(row[0] for row in main_rows.all())

    return found
