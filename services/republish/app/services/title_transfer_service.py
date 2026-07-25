"""
제목 이동 서비스
임시 제목(TempTitle) ↔ 정식 제목(MainTitle) 간 이동 처리
핵심 원칙: "지역명이 다르면 절대 그룹화하지 않음"
"""
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError

from ..models.title import MainTitle, TitleGroup, TempTitle
from ..core.logger import get_logger

import sys
import os

# Docker 환경과 로컬 환경 모두 지원
_shared_paths = ['/app/shared', '/home/jteen/blogauto_v2/shared']
for _path in _shared_paths:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
        break

from services.location_service import extract_location, normalize_location
from services.similarity_service import SimilarityService, DEFAULT_SIMILARITY_THRESHOLD

logger = get_logger("title_transfer", "title_transfer.log")


class TitleTransferService:
    """제목 이동 서비스"""

    def __init__(
        self,
        db: AsyncSession,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        user_id: int = 1,
    ):
        self.db = db
        self.threshold = threshold
        self.user_id = user_id
        self.similarity_service = SimilarityService(threshold)
        # 회색지대 AI 설정(move_to_main 시 로드) + 배치 판정 캐시
        self._sim_cfg: Dict[str, Any] = {}
        self._ai_cache: Dict[tuple, bool] = {}

    async def _load_similarity_config(self) -> Dict[str, Any]:
        """유사도 회색지대/AI 설정 로드(SystemSettings)."""
        from .system_settings_service import SystemSettingsService

        db = self.db
        return {
            "gray_lower": await SystemSettingsService.get_float(
                "similarity_gray_lower", db, 68.0
            ),
            "gray_upper": await SystemSettingsService.get_float(
                "similarity_gray_upper", db, 80.0
            ),
            "ai_enabled": await SystemSettingsService.get_bool(
                "similarity_ai_enabled", db, False
            ),
            "ai_provider": (await SystemSettingsService.get(
                "similarity_ai_provider", db, "") or ""),
            "ai_model": (await SystemSettingsService.get(
                "similarity_ai_model", db, "") or ""),
        }

    async def move_to_main(self, temp_title_ids: List[int], auto_group: bool = True) -> Dict[str, Any]:
        """
        임시 제목 → 정식 제목 이동

        이동 성공 시 임시 제목은 삭제됩니다.
        """
        result = {"moved": 0, "grouped": 0, "duplicates": 0, "deleted": 0, "errors": []}

        if not temp_title_ids:
            return result

        # === 1단계: 모든 필요한 데이터를 미리 조회 ===

        # 1-1. 모든 임시 제목을 한 번에 조회
        temp_query = select(TempTitle).where(TempTitle.id.in_(temp_title_ids))
        temp_result = await self.db.execute(temp_query)
        temp_titles = {t.id: t for t in temp_result.scalars().all()}

        # 1-2. 기존 정식 제목 조회 (중복 체크용) — Phase 1: 범위 축소
        # 기존: 전체 정식제목 title 을 set 으로 로딩(20만 시 메모리 폭증).
        # 변경: 전환 대상 임시제목의 title 과 겹치는 것만 IN 으로 조회.
        # "전환 title 이 기존에 있는가" 판정 결과는 동일(회귀 없음).
        temp_title_strings = [t.title for t in temp_titles.values()]
        existing_titles = set()
        if temp_title_strings:
            existing_result = await self.db.execute(
                select(MainTitle.title).where(
                    MainTitle.title.in_(temp_title_strings)
                )
            )
            existing_titles = set(row[0] for row in existing_result.all())

        # 1-3. 기존 그룹과 대표 제목 조회 (자동 그룹화용)
        groups_with_reps = []
        if auto_group:
            groups_query = select(TitleGroup).where(TitleGroup.is_active == True)
            groups_result = await self.db.execute(groups_query)
            groups = list(groups_result.scalars().all())

            # 대표 제목 ID 목록 추출
            rep_title_ids = [g.representative_title_id for g in groups if g.representative_title_id]

            # 대표 제목들을 한 번에 조회
            rep_titles_map = {}
            if rep_title_ids:
                rep_titles_query = select(MainTitle).where(MainTitle.id.in_(rep_title_ids))
                rep_titles_result = await self.db.execute(rep_titles_query)
                rep_titles_map = {t.id: t for t in rep_titles_result.scalars().all()}

            # representative_title_id가 없는 그룹의 멤버 제목도 조회
            groups_without_rep = [g for g in groups if not g.representative_title_id]
            if groups_without_rep:
                group_ids_without_rep = [g.id for g in groups_without_rep]
                # 각 그룹의 첫 번째 멤버를 대표로 사용
                member_query = select(MainTitle).where(MainTitle.group_id.in_(group_ids_without_rep))
                member_result = await self.db.execute(member_query)
                members_by_group = {}
                for m in member_result.scalars().all():
                    if m.group_id not in members_by_group:
                        members_by_group[m.group_id] = m

            # 그룹과 대표 제목 매핑
            for group in groups:
                if group.representative_title_id and group.representative_title_id in rep_titles_map:
                    groups_with_reps.append((group, rep_titles_map[group.representative_title_id]))
                elif not group.representative_title_id and group.id in members_by_group:
                    # representative_title_id가 없으면 그룹 멤버 중 첫 번째를 대표로 사용
                    groups_with_reps.append((group, members_by_group[group.id]))

        # === 2단계: 데이터 처리 (DB 조회 없이) ===

        # 생성할 MainTitle 목록
        main_titles_to_add = []
        # 삭제할 TempTitle ID 목록
        temp_ids_to_delete = []
        # 중복 처리할 TempTitle 목록
        duplicate_temp_ids = []
        # 새로 생성할 그룹 목록
        new_groups = []

        for temp_id in temp_title_ids:
            temp_title = temp_titles.get(temp_id)
            if not temp_title:
                result["errors"].append(f"ID {temp_id}: 제목을 찾을 수 없음")
                continue
            if temp_title.status == "moved":
                result["errors"].append(f"ID {temp_id}: 이미 이동됨")
                continue

            # 중복 체크: 정식/기존에 같은 제목이 있으면 임시제목을 삭제한다
            # (이동 조치한 제목은 status 만 바꿔 남기지 않고 제거)
            if temp_title.title in existing_titles:
                duplicate_temp_ids.append(temp_id)
                temp_ids_to_delete.append(temp_id)
                result["duplicates"] += 1
                continue

            # 지역명 추출
            location_info = extract_location(temp_title.title)
            location_json = json.dumps(location_info, ensure_ascii=False) if location_info else None

            # MainTitle 생성 준비
            main_title = MainTitle(
                title=temp_title.title,
                category_id=temp_title.topic_id,  # topic_id를 category_id로 매핑 (하위 호환)
                topic_id=temp_title.topic_id,
                subtopic_id=temp_title.subtopic_id,
                status="available",
                source="transfer",
                source_temp_title_id=temp_title.id,
                source_url=temp_title.source_post_url,
                location_info=location_json,
            )

            main_titles_to_add.append({
                'main_title': main_title,
                'temp_id': temp_id,
                'location_info': location_info,
            })

            # 기존 제목 set에 추가 (다음 중복 체크용)
            existing_titles.add(temp_title.title)

            # 삭제 대상에 추가
            temp_ids_to_delete.append(temp_id)

        # === 3단계: DB 저장 ===

        # 중복 제목은 status 변경이 아니라 삭제 대상(temp_ids_to_delete)에
        # 포함되어 아래 3단계에서 임시제목 테이블에서 제거된다.

        # MainTitle 개별 추가 (savepoint + IntegrityError 시 중복 스킵)
        items_added: List[Dict[str, Any]] = []
        for item in main_titles_to_add:
            savepoint = await self.db.begin_nested()
            self.db.add(item['main_title'])
            try:
                await savepoint.commit()
                items_added.append(item)
            except IntegrityError:
                await savepoint.rollback()
                title_text = item['main_title'].title
                logger.info(f"[TRANSFER] 중복 제목 스킵 (DB 제약): '{title_text[:30]}'")
                result["duplicates"] += 1
                # 중복(이미 정식 존재)이어도 임시제목은 삭제 대상 유지하여 제거
                continue
        main_titles_to_add = items_added

        # 그룹화 처리 (새 그룹 생성 포함)
        if auto_group:
            # 회색지대 AI 설정 로드 + 배치 캐시 초기화(1회)
            self._sim_cfg = await self._load_similarity_config()
            self._ai_cache = {}
            for item in main_titles_to_add:
                main_title = item['main_title']
                location_info = item['location_info']

                grouped = await self._auto_group_title(main_title, location_info, groups_with_reps, new_groups)
                if grouped:
                    result["grouped"] += 1

        # 새 그룹 일괄 추가
        for group in new_groups:
            self.db.add(group)

        # flush하여 그룹 ID 생성
        await self.db.flush()

        # 새 그룹의 representative_title_id 설정 및 제목의 group_id 설정
        for group in new_groups:
            if hasattr(group, '_pending_rep_title'):
                rep_title = group._pending_rep_title
                # 대표 제목 ID 설정
                group.representative_title_id = rep_title.id
                # 제목의 group_id 설정 (새 그룹이므로 이 시점에 group.id가 생성됨)
                rep_title.group_id = group.id
                logger.debug(f"[TRANSFER] 새 그룹 생성: group_id={group.id}, rep_title_id={rep_title.id}")

            # 새 그룹에 매칭된 멤버들의 group_id 설정
            if hasattr(group, '_pending_members'):
                for member_title in group._pending_members:
                    member_title.group_id = group.id
                    logger.debug(f"[TRANSFER] 그룹 멤버 연결: title_id={member_title.id}, group_id={group.id}")

        # 이동된 임시 제목 삭제
        if temp_ids_to_delete:
            delete_stmt = delete(TempTitle).where(TempTitle.id.in_(temp_ids_to_delete))
            await self.db.execute(delete_stmt)
            result["deleted"] = len(temp_ids_to_delete)

        result["moved"] = len(main_titles_to_add)

        await self.db.commit()
        logger.info(f"[TRANSFER] 이동: moved={result['moved']}, grouped={result['grouped']}, deleted={result['deleted']}")
        return result

    def _score_best_group(
        self,
        title: MainTitle,
        groups_with_reps: List[tuple],
    ) -> Optional[tuple]:
        """카테고리 일치 그룹 중 최고 유사도 후보 반환(임계값 무관).

        Returns: (group, rep_title, score) 또는 None
        """
        best = None
        best_score = -1.0
        for group, rep_title in groups_with_reps:
            if title.category_id and group.category_id != title.category_id:
                continue
            result = self.similarity_service.calculate_similarity_v3(
                title.title, rep_title.title
            )
            score = result["score"]
            if score > best_score:
                best_score = score
                best = (group, rep_title, score)
        return best

    async def _should_group(
        self, new_title: str, rep_title: str, score: float,
    ) -> bool:
        """밴드 판정: 상한↑ 그룹 / 하한↓ 분리 / 회색지대 AI(활성 시).

        AI 비활성 시 기존 동작(임계값 컷) 유지.
        """
        cfg = self._sim_cfg
        if cfg.get("ai_enabled") and cfg.get("ai_provider"):
            if score >= cfg["gray_upper"]:
                return True
            if score <= cfg["gray_lower"]:
                return False
            return await self._ai_same_topic(new_title, rep_title, cfg)
        return score >= self.threshold

    async def _ai_same_topic(
        self, a: str, b: str, cfg: Dict[str, Any],
    ) -> bool:
        """회색지대 두 제목이 같은 주제인지 저렴 AI로 판정(캐시)."""
        key = tuple(sorted((a.strip(), b.strip())))
        if key in self._ai_cache:
            return self._ai_cache[key]
        verdict = False
        try:
            from .ai.ai_service import AIService
            prompt = (
                "두 블로그 글 제목이 사실상 같은 주제·내용을 다루면 '예', "
                "다르면 '아니오'로만 답하세요.\n"
                f"제목1: {a}\n제목2: {b}\n답:"
            )
            ai = AIService(self.db, self.user_id)
            res = await ai.generate(
                prompt=prompt,
                provider=cfg["ai_provider"],
                model=(cfg["ai_model"] or None),
                max_tokens=8,
                temperature=0.0,
            )
            text = ((res or {}).get("content") or "").strip().lower()
            verdict = text.startswith(("예", "네", "yes", "y", "true", "1"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[TRANSFER] 회색지대 AI 판정 실패(분리 처리): {e}")
            verdict = False
        self._ai_cache[key] = verdict
        return verdict

    async def _auto_group_title(
        self,
        title: MainTitle,
        location_info: Optional[Dict],
        groups_with_reps: List[tuple],
        new_groups: List[TitleGroup],
    ) -> bool:
        """제목 자동 그룹화(밴드+회색지대 AI). attach/신규그룹 로직 유지."""
        best = self._score_best_group(title, groups_with_reps)
        if best is not None:
            group, rep_title, score = best
            if await self._should_group(title.title, rep_title.title, score):
                if group.id is not None:
                    title.group_id = group.id
                    if not group.representative_title_id:
                        title.is_group_representative = True
                        group.representative_title_id = title.id
                        logger.debug(
                            f"[TRANSFER] 대표 없는 그룹에 대표 설정: "
                            f"group_id={group.id}, title_id={title.id}"
                        )
                else:
                    if not hasattr(group, '_pending_members'):
                        group._pending_members = []
                    group._pending_members.append(title)
                title.similarity_score = score
                title.grouped_at = datetime.utcnow()
                group.member_count = (group.member_count or 0) + 1
                return True

        # 새 그룹 생성
        group_name = title.title[:30]
        if location_info:
            loc_str = normalize_location(location_info)
            if loc_str:
                group_name = f"[{loc_str}] {group_name}"
        group = TitleGroup(
            name=group_name,
            category_id=title.category_id,
            location=normalize_location(location_info) if location_info else None,
            member_count=1,
        )
        group._pending_rep_title = title
        title.is_group_representative = True
        title.grouped_at = datetime.utcnow()
        new_groups.append(group)
        groups_with_reps.append((group, title))
        return True

    async def move_to_temp(self, title_ids: List[int], move_entire_group: bool = True) -> Dict[str, Any]:
        """
        정식 제목 → 임시 제목 이동 (복구)

        정식 제목은 삭제되고, 임시 제목이 새로 생성됩니다.

        Args:
            title_ids: 이동할 정식 제목 ID 목록
            move_entire_group: True면 선택한 제목이 그룹 멤버인 경우 그룹 전체를 이동
        """
        result = {"moved": 0, "errors": [], "groups_moved": 0}

        if not title_ids:
            return result

        # === 1단계: 모든 필요한 데이터를 미리 조회 ===

        # 1-1. 모든 정식 제목을 한 번에 조회
        main_query = select(MainTitle).where(MainTitle.id.in_(title_ids))
        main_result = await self.db.execute(main_query)
        main_titles = {t.id: t for t in main_result.scalars().all()}

        # 1-1-1. 그룹 전체 이동 옵션: 선택된 제목의 그룹에 속한 모든 제목을 추가
        if move_entire_group:
            group_ids_to_move = set()
            for t in main_titles.values():
                if t.group_id:
                    group_ids_to_move.add(t.group_id)

            if group_ids_to_move:
                # 해당 그룹의 모든 멤버 조회
                group_members_query = select(MainTitle).where(MainTitle.group_id.in_(group_ids_to_move))
                group_members_result = await self.db.execute(group_members_query)
                for member in group_members_result.scalars().all():
                    if member.id not in main_titles:
                        main_titles[member.id] = member
                        title_ids.append(member.id)

                result["groups_moved"] = len(group_ids_to_move)
                logger.info(f"[TRANSFER] 그룹 전체 이동: {len(group_ids_to_move)}개 그룹, {len(main_titles)}개 제목")

        # 1-2. 삭제 대상을 representative_title_id로 참조하는 모든 그룹 조회 (실제 FK 기반)
        # 중요: 그룹 전체 이동으로 확장된 title_ids를 사용해야 함
        all_title_ids_to_delete = list(main_titles.keys())
        referencing_groups_query = select(TitleGroup).where(
            TitleGroup.representative_title_id.in_(all_title_ids_to_delete)
        )
        ref_groups_result = await self.db.execute(referencing_groups_query)
        referencing_groups = {g.representative_title_id: g for g in ref_groups_result.scalars().all()}

        # 1-3. 관련 그룹 조회 (멤버 카운트 업데이트용)
        group_ids = [t.group_id for t in main_titles.values() if t.group_id]
        groups_map = {}
        if group_ids:
            groups_query = select(TitleGroup).where(TitleGroup.id.in_(group_ids))
            groups_result = await self.db.execute(groups_query)
            groups_map = {g.id: g for g in groups_result.scalars().all()}

        # === 2단계: 데이터 처리 ===

        temp_titles_to_add = []
        main_ids_to_delete = []

        for title_id in title_ids:
            main_title = main_titles.get(title_id)
            if not main_title:
                result["errors"].append(f"ID {title_id}: 제목을 찾을 수 없음")
                continue

            # 임시 제목 생성 준비 (topic_id, subtopic_id 모두 복구)
            temp_title = TempTitle(
                title=main_title.title,
                source_blog_url=main_title.source_url or "",
                source_post_url=main_title.source_url or "",
                collection_stage="rollback",
                status="categorized",  # 카테고리 정보가 있으므로 categorized
                topic_id=main_title.topic_id,
                subtopic_id=main_title.subtopic_id,
            )
            temp_titles_to_add.append(temp_title)
            main_ids_to_delete.append(title_id)

            # 그룹 카운트 업데이트
            if main_title.group_id and main_title.group_id in groups_map:
                group = groups_map[main_title.group_id]
                group.member_count = max(0, (group.member_count or 1) - 1)

        # === 3단계: DB 저장 ===

        # 임시 제목 추가
        for temp_title in temp_titles_to_add:
            self.db.add(temp_title)

        # 모든 참조하는 그룹의 representative_title_id를 NULL로 설정 (FK 해제)
        # ORM 객체 수정 대신 직접 UPDATE 쿼리 실행으로 확실히 반영
        if all_title_ids_to_delete:
            update_stmt = update(TitleGroup).where(
                TitleGroup.representative_title_id.in_(all_title_ids_to_delete)
            ).values(representative_title_id=None)
            await self.db.execute(update_stmt)
            logger.info(f"[TRANSFER] FK 참조 해제: {len(all_title_ids_to_delete)}개 제목에 대한 그룹 참조 해제")

        # flush로 UPDATE 반영
        await self.db.flush()

        # 정식 제목 삭제 (참조 해제 후)
        if main_ids_to_delete:
            delete_stmt = delete(MainTitle).where(MainTitle.id.in_(main_ids_to_delete))
            await self.db.execute(delete_stmt)

        # 멤버가 없는 그룹 삭제 (referencing_groups와 groups_map 모두 확인)
        groups_to_delete = set()

        for group in referencing_groups.values():
            if (group.member_count or 0) <= 0:
                groups_to_delete.add(group.id)

        for group in groups_map.values():
            if (group.member_count or 0) <= 0:
                groups_to_delete.add(group.id)

        # 그룹 삭제
        if groups_to_delete:
            delete_groups_stmt = delete(TitleGroup).where(TitleGroup.id.in_(groups_to_delete))
            await self.db.execute(delete_groups_stmt)
            logger.info(f"[TRANSFER] 빈 그룹 삭제: {len(groups_to_delete)}개")

        result["moved"] = len(temp_titles_to_add)
        result["groups_deleted"] = len(groups_to_delete)

        await self.db.commit()
        logger.info(f"[TRANSFER] 복구: moved={result['moved']}, groups_deleted={len(groups_to_delete)}")
        return result

    async def auto_transfer_categorized(self) -> Dict[str, Any]:
        """카테고리가 있는 임시 제목 자동 이동"""
        query = select(TempTitle.id).where(
            TempTitle.topic_id.isnot(None),  # topic_id로 조회
            TempTitle.status.in_(["new", "categorized"])
        )
        result = await self.db.execute(query)
        temp_ids = [row[0] for row in result.all()]

        transfer_result = await self.move_to_main(temp_ids, auto_group=True)
        transfer_result["total"] = len(temp_ids)
        logger.info(f"[AUTO_TRANSFER] total={len(temp_ids)}, moved={transfer_result['moved']}")
        return transfer_result


# 편의 함수
async def move_temp_to_main(
    db: AsyncSession, temp_title_ids: List[int],
    auto_group: bool = True, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict[str, Any]:
    """임시 → 정식 이동"""
    return await TitleTransferService(db, threshold).move_to_main(temp_title_ids, auto_group)


async def move_main_to_temp(
    db: AsyncSession, title_ids: List[int], move_entire_group: bool = True
) -> Dict[str, Any]:
    """정식 → 임시 이동"""
    return await TitleTransferService(db).move_to_temp(title_ids, move_entire_group)


async def auto_transfer_categorized_titles(
    db: AsyncSession, threshold: float = DEFAULT_SIMILARITY_THRESHOLD
) -> Dict[str, Any]:
    """카테고리 있는 임시 제목 자동 이동"""
    return await TitleTransferService(db, threshold).auto_transfer_categorized()
