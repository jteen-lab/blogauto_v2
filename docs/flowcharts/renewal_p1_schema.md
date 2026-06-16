# 재발행 리뉴얼 P1 — 스키마·설정 기반 (2026-06-16)

전체 설계: [[bulk_replace_temp_consistency]] 이후 재발행 리뉴얼 기능. P1=기반(스키마/설정/백필).

## P1 범위
- `Blog.renewal_config`(JSON) 신설 — 리뉴얼 정책(블로그 단위 + 카테고리별).
- `CrawledPost.last_renewed_at`(DateTime) 신설 — 마지막 리뉴얼 시각(주기 판단 기준).
- alembic 044 마이그레이션(두 컬럼, nullable).
- 블로그 설정 "재발행/리뉴얼" GET/POST API.
- platform_post_id 백필(과거 발행분).

## renewal_config 구조
```json
{
  "default_period_months": 6,
  "title_mode": "keep | recombine",
  "delete_grace_days": 7,
  "category_periods": { "<subtopic_id>": 12 }
}
```
- 주기 해석: 글의 `subtopic_id` → `category_periods[subtopic_id]` 있으면 그 값, 없으면 `default_period_months`.
- category_periods는 그 블로그가 선택한 서브카테고리(`blog_categories.subtopic_id`)만 대상.

## 나이/주기 판정 (P3에서 사용, P1은 필드만)
```mermaid
flowchart TD
    A[리뉴얼 후보 글] --> B["나이기준 = last_renewed_at ?? published_at"]
    B --> C["주기 = category_periods[subtopic_id] ?? default_period_months"]
    C --> D{now - 나이기준 >= 주기(월)?}
    D -->|예| E[리뉴얼 대상]
    D -->|아니오| F[미도래 → 날짜만 갱신]
```

## 배포 주의 (신규 컬럼)
- 앱은 create_all만 사용 → 기존 테이블에 컬럼 자동 추가 안 됨. ORM이 전 컬럼 SELECT하므로 컬럼 없으면 Blog 조회 실패.
- 순서: 이미지 push → 서버 pull → **`docker compose run --rm app alembic upgrade head`(일회성, 구 앱 가동 중 컬럼만 추가)** → `up -d`(신 코드 기동, 컬럼 이미 존재).

## P1 비포함(후속)
- P2 리뉴얼 서비스(fetch→재생성→갱신, 제목/이미지 규칙), P3 게이트·스케줄러, P4 저장정리.
