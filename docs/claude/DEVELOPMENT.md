# 개발 가이드 상세

> CLAUDE.md에서 참조하는 상세 문서입니다.

## 기술 스택

### Backend
- **FastAPI** (신규 서비스)
- **Django 5.2.4** (레거시 blogauto_new - 참조만)
- **PostgreSQL** (production) / **SQLite** (development)
- **SQLAlchemy** (ORM)
- **Redis** (caching) / **APScheduler** (scheduling)

### Frontend
- **Alpine.js** (프론트엔드 프레임워크)
- **Jinja2** (템플릿 엔진)
- **Tailwind CSS** (스타일링)

## Docker 명령어

```bash
# 로컬 테스트
cd ~/blogauto_v2/services/republish
docker-compose down
docker-compose build --no-cache
docker-compose up -d
docker-compose logs app --tail 30

# 헬스체크
curl http://localhost:8001/health

# 테이블 확인
docker exec blogauto_db psql -U blogauto -d blogauto_v2 -c "\dt"

# pytest
pytest tests/
```

## 배포 (Oracle 서버)

```bash
ssh -i ~/.ssh/oci_blogauto.key ubuntu@158.180.66.204
cd ~/blogauto_v2/services/republish
git pull origin main
docker-compose down && docker-compose build --no-cache && docker-compose up -d
```

## 개발 프로세스

### Phase 1: Planning
```
- [ ] Feature requirements 정의
- [ ] Flowchart 작성 (docs/flowcharts/)
- [ ] 에이전트별 작업 범위 설계
- [ ] 예상 파일 목록 및 줄 수 추정
```

### Phase 2: Development
```
/multi-agent [기능명]을 구현해줘

자동 실행 흐름:
1. @explorer-agent: 레거시 분석 (필요 시)
2. @backend-agent: API/모델 구현
3. @frontend-agent: UI 구현
4. @reviewer-agent: 리뷰 및 테스트
```

### Phase 3: Review & Testing
```
- [ ] @reviewer-agent 코드 리뷰 완료
- [ ] 단위 테스트 작성
- [ ] 통합 테스트 통과
- [ ] 문서화 완료
```

### Phase 4: Deployment
```
- [ ] 파일별 개별 git add + commit
- [ ] 로컬 Docker 테스트
- [ ] Oracle 서버 배포
```

## 코드 표준

```python
# 필수 항목
- Type hints: MANDATORY
- Docstrings: MANDATORY
- Error handling: MANDATORY
- Logging: MANDATORY

# 예시
def publish(blog_id: int) -> bool:
    """Publish a blog post.

    Args:
        blog_id: Blog ID

    Returns:
        Success status
    """
    logger.info(f"[PUBLISH] Starting: {blog_id}")
    try:
        return True
    except Exception as e:
        logger.error(f"[PUBLISH] Failed: {e}")
        raise
```

## 로깅 규칙

```python
logger.info("[REPUBLISH] Starting process")
logger.error("[REPUBLISH_ERROR] Failed to publish")
logger.debug("[DB_QUERY] Fetching blogs")
```

## Context7 MCP 사용 기준

| 우선순위 | 트리거 |
|----------|--------|
| 필수 | FastAPI, SQLAlchemy, Pydantic, APScheduler 사용 시 |
| 필수 | 처음 사용하는 라이브러리 기능 |
| 필수 | 에러 해결 1회 실패 시 |
| 권장 | 버전별 차이 의심 시 |

## 파일 크기 모니터링

```bash
# 500줄 초과 파일 찾기
find . -name "*.py" -exec wc -l {} + | awk '$1 > 500'

# 초과 시 즉시 분리
# main.py (600줄) -> main.py (200) + handlers.py (200) + utils.py (200)
```
