"""
BlogAuto 표준 데이터 아이템

모든 모듈이 주고받는 표준 데이터 단위입니다.
n8n의 item 구조를 참고하여 설계되었습니다.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import uuid


@dataclass
class BinaryData:
    """바이너리 데이터 (파일, 이미지 등)"""
    data: bytes
    mime_type: str
    filename: Optional[str] = None
    size: Optional[int] = None

    def __post_init__(self):
        if self.size is None and self.data:
            self.size = len(self.data)


@dataclass
class ItemMeta:
    """아이템 메타데이터"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_module: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlogAutoItem:
    """
    모든 모듈이 주고받는 표준 데이터 단위

    Attributes:
        json: 일반 데이터 (필수)
        binary: 파일 데이터 (선택)
        meta: 메타데이터 (자동 생성)

    Example:
        item = BlogAutoItem(
            json={"keyword": "다이어트", "volume": 5000}
        )
    """
    json: dict[str, Any]
    binary: Optional[dict[str, BinaryData]] = None
    meta: Optional[ItemMeta] = None

    def __post_init__(self):
        if self.meta is None:
            self.meta = ItemMeta()

    def get(self, key: str, default: Any = None) -> Any:
        """json 데이터에서 값 조회"""
        return self.json.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """json 데이터에 값 설정"""
        self.json[key] = value

    def has_binary(self, key: str) -> bool:
        """바이너리 데이터 존재 여부"""
        return self.binary is not None and key in self.binary

    def get_binary(self, key: str) -> Optional[BinaryData]:
        """바이너리 데이터 조회"""
        if self.binary is None:
            return None
        return self.binary.get(key)

    def set_binary(self, key: str, data: BinaryData) -> None:
        """바이너리 데이터 설정"""
        if self.binary is None:
            self.binary = {}
        self.binary[key] = data

    def to_dict(self) -> dict:
        """직렬화"""
        result = {"json": self.json}
        if self.binary:
            result["binary"] = {
                k: {
                    "mime_type": v.mime_type,
                    "filename": v.filename,
                    "size": v.size
                }
                for k, v in self.binary.items()
            }
        if self.meta:
            result["meta"] = {
                "id": self.meta.id,
                "source_module": self.meta.source_module,
                "created_at": self.meta.created_at.isoformat(),
                "tags": self.meta.tags,
                "extra": self.meta.extra
            }
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "BlogAutoItem":
        """역직렬화"""
        meta = None
        if "meta" in data:
            meta_data = data["meta"]
            meta = ItemMeta(
                id=meta_data.get("id", str(uuid.uuid4())),
                source_module=meta_data.get("source_module"),
                created_at=datetime.fromisoformat(meta_data["created_at"])
                    if "created_at" in meta_data else datetime.now(),
                tags=meta_data.get("tags", []),
                extra=meta_data.get("extra", {})
            )
        return cls(json=data.get("json", {}), binary=None, meta=meta)


# 타입 별칭
ItemList = list[BlogAutoItem]
