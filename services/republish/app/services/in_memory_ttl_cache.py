"""
메모리 TTL 캐시 (Phase 4: 충돌감지 같은 read-heavy 엔드포인트용).

분산 환경(여러 app/워커 인스턴스)에서는 인스턴스 간 불일치 가능. 따라서
- 단일 app 인스턴스 또는
- 짧은 TTL(수십초)로 stale tolerance 가 있는 엔드포인트
에만 사용한다. 분산 일관성이 필요하면 Redis 캐시 도입 필요.

Thread-safe 보장 없음(단순 dict). FastAPI async 이벤트 루프 단일 스레드
기준에서 race condition 영향 무시 가능 수준.
"""
import time
from typing import Any, Optional

_store: dict[str, tuple[float, Any]] = {}


def cache_get(key: str, ttl: float) -> Optional[Any]:
    """key 가 ttl 초 이내 set 됐으면 값 반환, 아니면 None.

    만료된 항목은 lazy 삭제.
    """
    entry = _store.get(key)
    if entry is None:
        return None
    ts, val = entry
    if time.time() - ts >= ttl:
        _store.pop(key, None)
        return None
    return val


def cache_set(key: str, value: Any) -> None:
    """key 에 value 저장 (저장 시각 기록)."""
    _store[key] = (time.time(), value)


def cache_invalidate_prefix(prefix: str) -> int:
    """prefix 로 시작하는 모든 key 제거. 제거 개수 반환."""
    keys = [k for k in list(_store.keys()) if k.startswith(prefix)]
    for k in keys:
        _store.pop(k, None)
    return len(keys)
