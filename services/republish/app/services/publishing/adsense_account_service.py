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

        logger.info(
            "[ADSENSE_ACCOUNT] 동기화 완료 | id=%s | 사이트=%d건", account.id, len(sites)
        )
        return {"success": True, "account_id": account.id, "site_count": len(sites)}

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
