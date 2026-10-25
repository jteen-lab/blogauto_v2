"""리뉴얼 백업·기록·결과 검사 (2026-10-25).

- 백업: 라이브 글을 바꾸기 **전에** 원본 제목·HTML·이미지 주소를
  logs/renewal_backup/<블로그id>_<글번호>_<시각>.json 에 남긴다(되돌리기용).
- 기록: 글마다 logs/renewal.jsonl 한 줄 — 시각·판정·이유·옛 제목→새 제목·이미지 바뀜.
  마케팅이 4주 뒤 리뉴얼 글과 날짜만 바꾼 글의 유입을 비교한다.
- 검사: 새 본문에 옛 업로드 이미지(wp-content/uploads/2022~2025)가 남았는지.

순서도: docs/flowcharts/renewal_performance_pick.md (2. 한 글 리뉴얼)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.logger import LoggerConfig, get_logger

logger = get_logger("renewal_record", "app.log")

JOURNAL = "renewal.jsonl"
BACKUP_DIR = "renewal_backup"
_IMG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_OLD_UPLOAD = re.compile(r"/wp-content/uploads/20(1\d|2[0-5])/", re.IGNORECASE)


MIN_KEEP = 0.9   # 보강(augment)은 원래 글자의 90% 아래로 줄면 갱신하지 않는다
MIN_REWRITE = 1300   # 재작성(rewrite)은 줄어도 되지만 본문이 이보다 짧으면 갱신하지 않는다
MERGE_LIST = "renewal_merge_candidates.jsonl"


def _norm_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (url or "").strip()).rstrip("/").lower()


def strip_self_links(html: str, url: str) -> str:
    """이 글 자신으로 가는 링크를 뺀다('함께 볼 글' 버튼은 통째로, 본문 링크는 글자만 남김).

    리뉴얼 글은 DB 에 옛 제목으로 남아 있어 내부 링크가 자기 글을 고른다(/613 → /613).
    """
    me = _norm_url(url)
    if not me or not html:
        return html

    def mine(href: str) -> bool:
        return _norm_url(href) == me

    out = re.sub(r'<div class="button-link">\s*<a [^>]*href="([^"]+)"[^>]*>.*?</a>\s*</div>\s*',
                 lambda m: "" if mine(m.group(1)) else m.group(0), html, flags=re.S)
    return re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                  lambda m: m.group(2) if mine(m.group(1)) else m.group(0), out, flags=re.S)


def merge_candidate(blog: Any, row: Dict[str, Any]) -> None:
    """겹침 검사로 '제목 유지'가 나온 글 — 리뉴얼 대신 합치기 후보 목록에 한 줄(301 은 형 확인 뒤)."""
    try:
        p = Path(LoggerConfig.LOG_DIR) / MERGE_LIST
        p.parent.mkdir(parents=True, exist_ok=True)
        line = {"at": datetime.now().isoformat(timespec="seconds"),
                "blog_id": getattr(blog, "id", None), "blog": getattr(blog, "name", None), **row}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[RENEWAL_REC] 합치기 후보 기록 실패(무시) | %s", e)


def text_len(html: str) -> int:
    """태그·주석·공백을 뺀 글자 수."""
    return len(re.sub(r"\s+", "", re.sub(r"<[^>]+>|<!--.*?-->", "", html or "", flags=re.S)))


def image_urls(html: str) -> List[str]:
    """본문 그림 주소들."""
    return _IMG.findall(html or "")


def old_images(html: str) -> List[str]:
    """옛 업로드(2025년 이전 폴더) 그림 주소들. 리뉴얼 뒤엔 비어야 한다."""
    return [u for u in image_urls(html) if _OLD_UPLOAD.search(u)]


def backup(blog: Any, post_id: str, title: str, html: str) -> Optional[str]:
    """원본 백업 파일 경로. 실패하면 None(호출측이 갱신을 멈춘다)."""
    try:
        d = Path(LoggerConfig.LOG_DIR) / BACKUP_DIR
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        p = d / f"{getattr(blog, 'id', 0)}_{post_id}_{stamp}.json"
        p.write_text(json.dumps({
            "at": datetime.now().isoformat(timespec="seconds"),
            "blog_id": getattr(blog, "id", None), "blog": getattr(blog, "name", None),
            "post_id": post_id, "title": title, "images": image_urls(html),
            "html": html}, ensure_ascii=False), encoding="utf-8")
        return str(p)
    except Exception as e:  # noqa: BLE001
        logger.error("[RENEWAL_REC] 백업 실패 | blog=%s | post=%s | %s",
                     getattr(blog, "name", None), post_id, e)
        return None


def journal(blog: Any, row: Dict[str, Any]) -> None:
    """글마다 한 줄. 실패해도 리뉴얼 결과는 그대로."""
    try:
        p = Path(LoggerConfig.LOG_DIR) / JOURNAL
        p.parent.mkdir(parents=True, exist_ok=True)
        line = {"at": datetime.now().isoformat(timespec="seconds"),
                "blog_id": getattr(blog, "id", None),
                "blog": getattr(blog, "name", None), **row}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("[RENEWAL_REC] 기록 실패(무시) | %s", e)
