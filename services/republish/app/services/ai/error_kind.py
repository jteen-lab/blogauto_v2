"""AI 호출 실패를 '키 탓' 과 '일시 장애' 로 나눈다 (2026-10-17).

키를 ERROR 로 바꾸면 자동으로 되살아나지 않는다(rate_limited 만 15분 뒤 복구).
그래서 한 번의 일시 장애로 키를 ERROR 로 찍으면, 그 제공자만 쓰는 프리셋은
사람이 키를 다시 켤 때까지 "모든 제공자 호출 실패" 로 영구히 멈춘다.

실제 사례: 딥시크가 900초 붙잡다 choices 없는 응답을 돌려줌
→ ``'NoneType' object is not subscriptable`` → 키 ERROR 고착
→ 딥시크를 쓰는 프리셋(이사노트 등) 이틀간 생성 0건. 키 자체는 멀쩡했다.

원칙: 키가 정말 쓸 수 없다는 증거(인증 실패·권한 없음·잔액 없음)가 있을 때만
키 탓으로 본다. 그 밖(시간 초과·연결 끊김·서버 5xx·빈 응답·모델 이름 오류·
코드 예외)은 키를 그대로 두고 이번 호출만 실패시킨다.
"""
from __future__ import annotations

from typing import Optional

# 키를 바꿔야만 풀리는 HTTP 상태: 인증 실패 / 잔액 부족 / 권한 없음
_KEY_FAULT_STATUS = {401, 402, 403}

# 상태 코드를 못 얻을 때(httpx 등 문자열만 있는 예외) 쓰는 단서
_KEY_FAULT_HINTS = (
    "invalid api key",
    "incorrect api key",
    "invalid_api_key",
    "api key not valid",
    "api_key_invalid",
    "authentication",
    "unauthorized",
    "permission denied",
    "insufficient balance",
    "insufficient_quota",
)


def _status_code(exc: BaseException) -> Optional[int]:
    """예외에서 HTTP 상태 코드를 꺼낸다(openai·httpx 예외 공통).

    Args:
        exc: 호출 중 발생한 예외

    Returns:
        상태 코드, 없으면 None
    """
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def is_key_fault(exc: BaseException) -> bool:
    """이 실패가 키를 ERROR 로 표시할 만한 '키 탓' 인지 판정한다.

    Args:
        exc: 호출 중 발생한 예외

    Returns:
        인증·권한·잔액 문제면 True, 일시 장애·기타 예외면 False
    """
    code = _status_code(exc)
    if code is not None:
        return code in _KEY_FAULT_STATUS
    message = str(exc).lower()
    return any(hint in message for hint in _KEY_FAULT_HINTS)
