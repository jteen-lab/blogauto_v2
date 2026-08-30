"""애드센스 계정 등록·동기화 서비스 (다중 계정).

계정마다 refresh token을 보관하고, 동기화 시 각 계정의 사이트 목록을 받아
`adsense_sites` 에 캐시한다. 블로그 상태 판정은 이 캐시를 도메인 인덱스로 만들어
`adsense_status_resolver` 가 수행한다.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.encryption import decrypt_api_key, encrypt_api_key
from ...core.logger import get_logger
from ...models.adsense_account import AdsenseAccount, AdsenseSite
from .adsense_api import AdsenseApiError, fetch_account_sites
from .adsense_status_resolver import build_sites_index

logger = get_logger("adsense_account_service", "app.log")


class AdsenseAccountService:
    """애드센스 계정 CRUD + 사이트 동기화."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_accounts(self, user_id: int) -> List[AdsenseAccount]:
        result = await self.db.execute(
            select(AdsenseAccount)
            .where(AdsenseAccount.user_id == user_id)
            .options(selectinload(AdsenseAccount.sites))
            .order_by(AdsenseAccount.id)
        )
        return list(result.scalars().all())

    async def add_account(
        self, user_id: int, label: str, refresh_token: str,
        google_email: Optional[str] = None,
    ) -> AdsenseAccount:
        """계정을 등록한다(토큰은 암호화 저장)."""
        account = AdsenseAccount(
            user_id=user_id,
            label=label.strip() or "애드센스 계정",
            google_email=(google_email or "").strip() or None,
            refresh_token_encrypted=encrypt_api_key(refresh_token.strip()),
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        logger.info("[ADSENSE_ACCOUNT] 등록 | id=%s | label=%s", account.id, account.label)
        return account

    async def delete_account(self, user_id: int, account_id: int) -> bool:
        account = await self._get_owned(user_id, account_id)
        if not account:
            return False
        await self.db.delete(account)
        await self.db.commit()
        logger.info("[ADSENSE_ACCOUNT] 삭제 | id=%s", account_id)
        return True

    async def sync_account(self, user_id: int, account_id: int) -> Dict[str, Any]:
        """한 계정의 사이트 목록을 새로 받아 캐시를 교체한다."""
        account = await self._get_owned(user_id, account_id)
        if not account:
            return {"success": False, "error": "계정을 찾을 수 없습니다"}

        try:
            token = decrypt_api_key(account.refresh_token_encrypted)
        except Exception as exc:  # noqa: BLE001
            return await self._record_error(account, f"토큰 복호화 실패: {exc}")

        try:
            resource, sites = await fetch_account_sites(token, account.account_resource)
        except AdsenseApiError as exc:
            return await self._record_error(account, exc.message)
        except Exception as exc:  # noqa: BLE001
            return await self._record_error(account, f"동기화 오류: {exc}")

        # 캐시 교체(사이트가 애드센스에서 삭제된 경우도 반영)
        await self.db.execute(
            delete(AdsenseSite).where(AdsenseSite.account_id == account.id)
        )
        for site in sites:
            domain = (site.get("domain") or "").strip().lower()
            if not domain:
                continue
            self.db.add(AdsenseSite(
                account_id=account.id,
                domain=domain,
                state=(site.get("state") or "").upper() or None,
                site_resource=site.get("name"),
            ))

        account.account_resource = resource
        account.last_synced_at = datetime.now(timezone.utc)
        account.last_sync_error = None
        await self.db.commit()

        # 실제 상태를 블로그의 adsense_status 에 반영(승인 감지 → 전용 설정 해제)
        applied = await self.apply_statuses_to_blogs(account.user_id)

        logger.info(
            "[ADSENSE_ACCOUNT] 동기화 완료 | id=%s | 사이트=%d건 | 상태변경=%d건",
            account.id, len(sites), applied,
        )
        return {
            "success": True, "account_id": account.id,
            "site_count": len(sites), "status_updated": applied,
        }

    async def apply_statuses_to_blogs(self, user_id: int) -> int:
        """동기화된 사이트 상태를 블로그의 `adsense_status` 에 반영한다.

        표시는 조회 때마다 계산하지만, **모듈 실행 판정**(adsense_role)은 블로그의
        저장된 상태를 보므로 실제 값도 맞춰 둬야 한다. 그래야 승인된 블로그에서
        애드센스 전용 모듈이 자동으로 빠진다.

        사용자가 직접 '심사중'으로 표시해 둔 것은 덮지 않는다(애드센스가 아직
        '준비 중'으로 보고할 때 신청 사실은 사용자만 알기 때문).

        Returns:
            변경된 블로그 수
        """
        from ...models.blog import Blog
        from .adsense_status_resolver import (
            ST_APPLIED, ST_ATTENTION, ST_PREPARING, resolve_display_status,
        )

        index = await self.sites_index(user_id)
        if not index:
            return 0

        rows = await self.db.execute(
            select(Blog).where(
                Blog.user_id == user_id,
                Blog.is_deleted == False,  # noqa: E712
            )
        )
        changed = 0
        for blog in rows.scalars().all():
            verdict = resolve_display_status(blog, index)
            new_status = verdict["status"]

            # 사용자가 신청했다고 표시한 상태는 유지
            if new_status == ST_PREPARING and blog.adsense_status == ST_APPLIED:
                continue
            # '확인 필요'는 표시 전용 — 저장 상태는 건드리지 않는다
            if new_status == ST_ATTENTION:
                continue

            if blog.adsense_status != new_status:
                logger.info(
                    "[ADSENSE_ACCOUNT] 블로그 상태 갱신 | %s | %s → %s",
                    blog.name, blog.adsense_status, new_status,
                )
                blog.adsense_status = new_status
                # 승인으로 올라가면 모듈 프롬프트를 니치용으로 교체한다(S2).
                if new_status == "approved":
                    from ..generation.adsense_prompt_sync import sync_for_blog
                    await sync_for_blog(self.db, blog)
                changed += 1

        if changed:
            await self.db.commit()
        return changed

    async def sync_all(self, user_id: int) -> Dict[str, Any]:
        """활성 계정 전체 동기화. 한 계정이 실패해도 나머지는 진행한다."""
        accounts = await self.list_accounts(user_id)
        results = []
        for account in accounts:
            if not account.is_active:
                continue
            results.append(await self.sync_account(user_id, account.id))
        ok = sum(1 for r in results if r.get("success"))
        return {"success": True, "synced": ok, "total": len(results), "results": results}

    async def sites_index(self, user_id: int) -> Dict[str, AdsenseSite]:
        """모든 계정의 사이트를 도메인 인덱스로 병합해 반환."""
        result = await self.db.execute(
            select(AdsenseSite)
            .join(AdsenseAccount, AdsenseAccount.id == AdsenseSite.account_id)
            .where(
                AdsenseAccount.user_id == user_id,
                AdsenseAccount.is_active == True,  # noqa: E712
            )
        )
        return build_sites_index(list(result.scalars().all()))

    async def _get_owned(self, user_id: int, account_id: int) -> Optional[AdsenseAccount]:
        result = await self.db.execute(
            select(AdsenseAccount).where(
                AdsenseAccount.id == account_id,
                AdsenseAccount.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _record_error(self, account: AdsenseAccount, message: str) -> Dict[str, Any]:
        account.last_sync_error = message[:500]
        account.last_synced_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.error("[ADSENSE_ACCOUNT] 동기화 실패 | id=%s | %s", account.id, message)
        return {"success": False, "account_id": account.id, "error": message}
