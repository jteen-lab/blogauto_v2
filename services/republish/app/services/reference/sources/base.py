"""외부 자료원 공통 형태.

어댑터마다 응답 구조가 다르다. 공통 형태로 바꿔 놓아야 참조 파이프라인이
소스를 몰라도 된다.

    금감원        {"result": {"baseList": [{"intr_rate": 4.2, ...}]}}
    공공데이터포털 {"response": {"body": {"items": {"item": [...]}}}}
                              ↓
                     SourceFact (공통)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceFact:
    """1차 출처에서 얻은 사실 하나.

    웹문서 요약과 달리 **출처가 분명하고 값이 구조화**돼 있다. 그래서
    프롬프트에서도 따로 표시해 AI 가 이쪽을 우선하게 한다.
    """

    title: str                                  # 무엇에 대한 값인가
    fields: Dict[str, Any] = field(default_factory=dict)   # 항목: 값
    source_name: str = ""                       # 기관명
    url: str = ""                               # 확인처
    published: str = ""                         # 기준일(있으면)

    def to_lines(self) -> List[str]:
        """사람이 읽을 줄 목록. 빈 값은 적지 않는다 — 빈칸을 보여 주면
        AI 가 그 자리를 상상으로 채운다."""
        out = [f"· {self.title}"] if self.title else []
        for key, value in self.fields.items():
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in ("none", "null", "-"):
                out.append(f"  - {key}: {text}")
        return out


@dataclass
class SourceResult:
    """한 소스의 조회 결과."""

    code: str
    name: str
    facts: List[SourceFact] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.facts) and not self.error

    def to_prompt(self) -> str:
        """프롬프트에 넣을 형태.

        웹문서 요약보다 **앞에** 놓고, 공식 자료임을 밝힌다. AI 가 두
        자료가 다를 때 어느 쪽을 믿을지 알아야 한다.
        """
        if not self.facts:
            return ""
        lines = [f"[공식 자료 — {self.name}]",
                 "아래는 기관이 공시한 값입니다. 웹 문서와 다르면 이쪽을 따르세요."]
        for fact in self.facts:
            lines.extend(fact.to_lines())
            if fact.url:
                lines.append(f"  - 확인처: {fact.url}")
        return "\n".join(lines)


class SourceAdapter:
    """어댑터 인터페이스.

    구현체는 `fetch()` 하나만 채우면 된다. 실패는 예외를 던지지 말고
    `SourceResult(error=...)` 로 돌려준다 — 소스 하나 때문에 글 생성이
    멈추면 안 된다.
    """

    code: str = ""

    async def fetch(self, source: Any, query: str,
                    entities: List[str]) -> SourceResult:
        """이 소스에서 질의에 해당하는 사실을 가져온다.

        Args:
            source: ExternalSource 행(endpoint·auth·options)
            query: 검색 질의(재작성된 것)
            entities: 제목에서 뽑은 개체. 결과를 좁히는 데 쓴다.

        Returns:
            SourceResult. 못 찾으면 facts 가 빈 목록이다(오류 아님).
        """
        raise NotImplementedError


def decrypt_key(source: Any) -> Optional[str]:
    """등록된 인증키를 푼다. 실패는 None — 그 소스만 건너뛴다."""
    from ....core.encryption import decrypt_api_key
    from ....core.logger import get_logger

    raw = getattr(source, "auth_key_encrypted", None)
    if not raw:
        return None
    try:
        return decrypt_api_key(raw)
    except Exception:  # noqa: BLE001
        get_logger("reference_sources", "app.log").warning(
            "[REF_SOURCE] 인증키 복호화 실패 | code=%s",
            getattr(source, "code", "?"))
        return None
