"""AI 호출 실패 판정(키 탓 vs 일시 장애) 테스트."""
import httpx
import openai

from app.services.ai.error_kind import is_key_fault


def _openai_error(cls: type, status: int) -> Exception:
    """상태 코드를 가진 openai 예외를 만든다."""
    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    resp = httpx.Response(status, request=req)
    return cls("x", response=resp, body=None)


def test_인증_실패는_키_탓() -> None:
    """401·403·402 는 키를 바꿔야 풀리므로 키 탓이다."""
    assert is_key_fault(_openai_error(openai.AuthenticationError, 401))
    assert is_key_fault(_openai_error(openai.PermissionDeniedError, 403))
    assert is_key_fault(_openai_error(openai.APIStatusError, 402))


def test_일시_장애는_키_탓_아님() -> None:
    """빈 응답·시간 초과·5xx·모델 오류(400)는 키를 그대로 둔다."""
    assert not is_key_fault(TypeError("'NoneType' object is not subscriptable"))
    assert not is_key_fault(RuntimeError("빈 응답(choices 없음) | model=x"))
    assert not is_key_fault(openai.APITimeoutError(request=httpx.Request("POST", "https://a")))
    assert not is_key_fault(_openai_error(openai.InternalServerError, 503))
    assert not is_key_fault(_openai_error(openai.BadRequestError, 400))


def test_상태코드_없는_문자열_단서() -> None:
    """상태 코드가 없으면 메시지 단서로 판정한다."""
    assert is_key_fault(Exception("API key not valid. Please pass a valid API key."))
    assert not is_key_fault(Exception("connection reset by peer"))
