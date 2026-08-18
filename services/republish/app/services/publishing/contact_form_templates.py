"""문의폼 기본 템플릿 카탈로그 (F10 확장, contact_form 모듈용).

블로그별로 다른 문의폼을 획일 관리하기 위한 재사용 템플릿. 업데이트로 항목을
추가할 수 있다. 필드 타입은 **Tally 실호출로 확정 검증된 타입만** 사용
(text/email/phone/number/textarea). 드롭다운·객관식 등은 스키마 확정 후 후속 추가.

각 필드: {"label": str, "type": Tally블록타입, "required": bool}
"""
from __future__ import annotations

from typing import Any, Dict, List

# Tally 확정 검증 필드 타입(단순 라벨+입력 구조)
SUPPORTED_FIELD_TYPES = (
    "INPUT_TEXT",
    "INPUT_EMAIL",
    "INPUT_PHONE_NUMBER",
    "INPUT_NUMBER",
    "TEXTAREA",
)


def _f(label: str, type_: str, required: bool = True) -> Dict[str, Any]:
    return {"label": label, "type": type_, "required": required}


# 기본 3필드(모듈 미배정 블로그 폴백)
DEFAULT_FIELDS: List[Dict[str, Any]] = [
    _f("이름", "INPUT_TEXT"),
    _f("이메일", "INPUT_EMAIL"),
    _f("문의 내용", "TEXTAREA"),
]

# 기본 제공 템플릿(6종). 업데이트로 확장 가능.
TEMPLATES: List[Dict[str, Any]] = [
    {
        "code": "basic",
        "name": "기본",
        "description": "이름·이메일·문의 내용",
        "title_template": "{blog} 문의",
        "fields": [_f("이름", "INPUT_TEXT"), _f("이메일", "INPUT_EMAIL"),
                   _f("문의 내용", "TEXTAREA")],
    },
    {
        "code": "simple",
        "name": "간단형",
        "description": "이메일·문의 내용만",
        "title_template": "{blog} 문의",
        "fields": [_f("이메일", "INPUT_EMAIL"), _f("문의 내용", "TEXTAREA")],
    },
    {
        "code": "with_phone",
        "name": "연락처 포함",
        "description": "이름·이메일·전화번호·문의 내용",
        "title_template": "{blog} 문의",
        "fields": [_f("이름", "INPUT_TEXT"), _f("이메일", "INPUT_EMAIL"),
                   _f("전화번호", "INPUT_PHONE_NUMBER", required=False),
                   _f("문의 내용", "TEXTAREA")],
    },
    {
        "code": "with_subject",
        "name": "제목 포함",
        "description": "이름·이메일·제목·문의 내용",
        "title_template": "{blog} 문의",
        "fields": [_f("이름", "INPUT_TEXT"), _f("이메일", "INPUT_EMAIL"),
                   _f("제목", "INPUT_TEXT"), _f("문의 내용", "TEXTAREA")],
    },
    {
        "code": "business",
        "name": "비즈니스/제휴",
        "description": "담당자·이메일·회사(사이트)·문의 내용",
        "title_template": "{blog} 제휴·비즈니스 문의",
        "fields": [_f("담당자명", "INPUT_TEXT"), _f("이메일", "INPUT_EMAIL"),
                   _f("회사/사이트", "INPUT_TEXT", required=False),
                   _f("문의 내용", "TEXTAREA")],
    },
    {
        "code": "detailed",
        "name": "상세형",
        "description": "이름·이메일·전화번호·제목·문의 내용",
        "title_template": "{blog} 문의",
        "fields": [_f("이름", "INPUT_TEXT"), _f("이메일", "INPUT_EMAIL"),
                   _f("전화번호", "INPUT_PHONE_NUMBER", required=False),
                   _f("제목", "INPUT_TEXT"), _f("문의 내용", "TEXTAREA")],
    },
]


def get_template(code: str) -> Dict[str, Any]:
    """코드로 템플릿 조회(없으면 KeyError)."""
    for t in TEMPLATES:
        if t["code"] == code:
            return t
    raise KeyError(f"알 수 없는 문의폼 템플릿: {code}")


def list_templates() -> List[Dict[str, Any]]:
    """UI용 템플릿 목록(코드·이름·설명·필드 수)."""
    return [
        {"code": t["code"], "name": t["name"], "description": t["description"],
         "field_count": len(t["fields"])}
        for t in TEMPLATES
    ]
