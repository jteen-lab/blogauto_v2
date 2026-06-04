# 워커 UI 프로그레스바 작업 계획서

> **버전**: v1.0 / **작성일**: 2026-05-10 / **대상**: BlogAuto v2 (`services/republish`)
> **범위**: 요약탭 바의 다중 워커(생성/발행/유틸) 카드에 진행률 시각화 추가

---

## 1. 배경 및 목적

### 1.1 현재 상태
- 다중 Celery 워커 운영 (generation / publish / utility / image)
- `dashboard_celery.py:/workers` 엔드포인트가 워커별 `status`/`active_tasks`/`processed`/`concurrency`/`uptime` 제공
- 요약탭 바(`global_summary.html`) PC + 모바일에 워커 카드 3개 표시
  - 표시 정보: 라벨, 점(dot, 상태 색), active_tasks 숫자, 툴팁
- 3초 간격 폴링으로 실시간 갱신

### 1.2 사용자 요구
1. 워커 카드에 **프로그레스바** 추가
2. 작업 진행률에 따라 **카드 색상이 좌측에서 우측으로 채워짐**
3. **별도 진행률 표시** (숫자/퍼센트)

### 1.3 검토 후 보강 사항
| 항목 | 사용자 제안 | 보강 |
|------|----------|------|
| 진행률 기준 | 모호 | **active_tasks ÷ concurrency** (워커 점유율 0~100%) |
| 시각화 | 좌측에서 색상 변화 | **CSS linear-gradient** 카드 자체 채움 + **인라인 프로그레스바** 병행 |
| 표시 | 별도 진행률 | 카드 내 숫자(N/M) + 우측 % 표시 |
| 상태 구분 | - | **idle / busy / saturated / offline** 4단계 색상 |
| 인터랙션 | - | 호버 시 상세 툴팁(현재 작업 task_name + 처리량) |
| 애니메이션 | - | width transition + 새 작업 시작 시 펄스 효과 |
| 접근성 | - | ARIA `role="progressbar"` + `aria-valuenow` |
| 모바일 대응 | - | 모바일 카드도 동일 구조, 좁은 폭 최적화 |
| 초과 점유 | - | active_tasks > concurrency 시 경고 색(saturated) |

---

## 2. 진행률 정의

### 2.1 핵심 공식
```
progress = min(100, round(active_tasks / max(concurrency, 1) * 100))
```
- `concurrency`가 0이거나 missing이면 분모를 1로 fallback
- 100% 초과 케이스(예: prefetch로 active > concurrency)는 saturated 상태로 별도 표시

### 2.2 상태 분류
| 상태 | 조건 | 카드 색 | 점 색 |
|------|------|--------|------|
| **offline** | `status === 'offline'` | red-50 / red-200 border | red-400 |
| **idle** | active=0 + online | green-50 / green-200 | green-400 |
| **busy** | 0 < active ≤ concurrency | primary 그라데이션 (좌→우) | blue-400 (animate-pulse) |
| **saturated** | active > concurrency | amber 그라데이션 + 강조 | amber-500 (animate-pulse) |
| **unknown** | status=unknown | gray-100 | gray-500 |

### 2.3 워커별 작업 종류 매핑 (툴팁용)
| 워커 키 | 처리 작업 |
|--------|---------|
| generation | 글 생성 (recombine/generate_content/generate_image) |
| publish | 발행/재발행 (publish_post/republish_post) |
| utility | 수집/이동 (collect_keywords/transfer_titles) |
| image | 이미지 생성 (generate_image) |

> **참고**: 현재 `WORKER_KEY_MAP`에는 image가 누락되어 있어 같이 보완 (별도 PR 또는 본 작업 포함).

---

## 3. UI/UX 설계

### 3.1 PC 카드 구조 (요약탭 바)
```
┌──────────────────────────────────┐
│ [생성 워커] ●  3  60%            │ ← 카드 외형
│▓▓▓▓▓▓▓▓▓░░░░░░░                  │ ← 좌→우 그라데이션 채움
└──────────────────────────────────┘
```

- 카드 자체에 `linear-gradient(to right, primary 60%, primary-lt 60%)` 적용
- 우측에 `60%` 텍스트 노출
- 점(dot)은 기존 위치 유지

### 3.2 CSS 그라데이션 구현
```css
.worker-card {
  background: linear-gradient(
    to right,
    var(--worker-progress-color) calc(var(--worker-progress) * 1%),
    var(--worker-bg-color) calc(var(--worker-progress) * 1%)
  );
  transition: background 0.4s ease-out;
}
```
- `--worker-progress`: 0~100 (Alpine x-style binding)
- `--worker-progress-color`: 상태별 색상 (busy=primary, saturated=amber)
- `--worker-bg-color`: 카드 기본 배경

### 3.3 인라인 프로그레스바(선택, 점선 영역)
- 카드 그라데이션이 진행률을 표현하지만, 명확성을 위해 카드 하단 1.5px 라인 형태로 추가
- 카드 외형이 너무 화려해지면 라인은 생략 가능 (사용자 피드백 후 결정)

### 3.4 표시 텍스트
- 라벨: `생성 워커`
- 점: 기존 `getWorkerDotClass`
- active_tasks: `3` (현재 표시값)
- **신규**: `60%` (진행률, active>0일 때만)

### 3.5 호버 툴팁
- 기존: `${labels[key]} 워커: 온라인 (활성 ${active_tasks}개)`
- 신규: 다음 정보 추가
  - `처리량: ${processed}건`
  - `동시 처리: ${active_tasks}/${concurrency}`
  - `가동시간: ${uptime}`

### 3.6 애니메이션
- 진행률 변화: `transition: background 0.4s ease-out` (부드러운 전환)
- 새 작업 시작(active_tasks 증가): 0.3초 펄스 효과 (`animate-ping` 1회)
- saturated 상태: 점에 `animate-pulse` 지속

### 3.7 모바일 대응
- 카드 폭이 좁아도 (모바일 grid 2열) 그라데이션 유지
- 진행률 텍스트는 카드 폭 < 120px일 때 생략, active_tasks만 표시
- 점 + 그라데이션으로 시각적 구분 충분

### 3.8 접근성
```html
<div role="progressbar"
     :aria-valuenow="progress"
     aria-valuemin="0"
     aria-valuemax="100"
     :aria-label="`${label} 워커 진행률 ${progress}%`">
  ...
</div>
```

---

## 4. 데이터 흐름

### 4.1 백엔드
- 기존: `/api/v1/dashboard/celery/workers` 응답에 `concurrency` 포함됨 → **추가 변경 불필요**
- 변경 없음: `_inspect_workers` 캐시 10초 TTL 유지

### 4.2 프론트엔드
- 기존: 3초 폴링 → `workerStatus.workers[key]` 갱신
- 신규: `getWorkerProgress(key)` 헬퍼 추가
  ```javascript
  getWorkerProgress(key) {
      const w = this.workerStatus?.workers?.[key];
      if (!w || w.status !== 'online') return 0;
      const active = Math.max(0, w.active_tasks || 0);
      const max = Math.max(1, w.concurrency || 1);
      return Math.min(100, Math.round(active / max * 100));
  }
  ```
- 신규: `getWorkerProgressColor(key)` 상태별 색상 클래스
- 신규: `getWorkerCardStyle(key)` 인라인 style 객체 (CSS variables)

---

## 5. 구현 단계

### Phase 1: 백엔드 검증 (0.5h)
- [x] `concurrency` 필드 응답 확인 (이미 포함됨)
- [ ] image 워커 `WORKER_KEY_MAP` 추가 (선택)

### Phase 2: GlobalSummary.js 메서드 추가 (1h)
- [ ] `getWorkerProgress(key)` 헬퍼
- [ ] `getWorkerProgressColor(key)`
- [ ] `getWorkerCardStyle(key)` (CSS variables 출력)
- [ ] `getWorkerTooltip(key)` 확장 (processed/uptime 포함)

### Phase 3: HTML 템플릿 변경 (1h)
- [ ] PC 카드 구조 변경 (`global_summary.html` 23~42)
  - 그라데이션 적용 + 진행률 텍스트 추가
- [ ] 모바일 카드 동일 구조 (`global_summary.html` 61~82)
- [ ] 접근성 ARIA 속성 추가

### Phase 4: CSS 스타일 (0.5h)
- [ ] `worker-card` 클래스 정의 (전역 CSS 또는 인라인)
- [ ] 그라데이션 transition + 펄스 애니메이션
- [ ] 다크/라이트 모드 호환 색상 변수

### Phase 5: 테스트 (1h)
- [ ] 0% (idle): 카드 빈 상태 + 점 녹색
- [ ] 50% (busy): 절반 채움 + 진행률 텍스트
- [ ] 100% (saturated 직전): 가득 채움
- [ ] 100%+ (saturated): amber 색 + 점 pulse
- [ ] offline: red 카드 + 진행률 미표시
- [ ] 모바일 좁은 폭에서 깨지지 않음
- [ ] 키보드 포커스 + 스크린 리더 접근성
- [ ] 3초 폴링 시 부드러운 transition 확인

### Phase 6: 캐시 버스팅 + 배포 (0.5h)
- [ ] `base.html`의 `?v=` 갱신
- [ ] `docker-compose down && up -d`
- [ ] 사용자 검증

**총 예상 시간**: 4.5시간

---

## 6. 위험 요소 및 대응

| 위험 | 영향 | 대응 |
|-----|-----|------|
| `concurrency`가 0이거나 missing | 0으로 나누기 | `Math.max(1, concurrency)` fallback |
| 모바일 좁은 폭에서 텍스트 잘림 | UX 저하 | 폭별 조건부 렌더링 (% 텍스트 생략) |
| 그라데이션 transition이 너무 빠르거나 느림 | 시각적 거슬림 | 0.4s ease-out 기본, 사용자 피드백 후 조정 |
| 활성 task 0인데 진행률 0%로 표시 | 사용자 오해(안 도는 것처럼 보임) | idle 상태로 명확히 구분 (배경 단색 녹색) |
| Celery prefetch로 active > concurrency | 진행률 100% 초과 | saturated 상태로 처리 (100% cap + amber 강조) |
| 폴링 누락 시 stale 표시 | 부정확한 진행률 | 응답 timestamp 기반 stale 감지 (>10초 → 회색) |
| 다크 테마 적용 시 색상 안 보임 | 가독성 저하 | CSS 변수 + 테마별 대응 |

---

## 7. 보강 아이디어 (선택, 향후 확장)

### 7.1 워커 카드 클릭 시 상세 모달
- 현재 처리 중인 task 목록 (Celery `inspect.active()` 응답 그대로 표시)
- 최근 완료 task 5건 (처리 시간, blog_id, 에러 여부)
- 워커 재시작 버튼 (관리자 전용)

### 7.2 시간별 진행률 그래프
- 별도 페이지 또는 모달
- 1시간/24시간 단위로 평균 점유율 표시
- 피크 시간대 식별

### 7.3 큐 등록 시 즉시 반영
- 폴링 3초를 기다리지 않고 dispatch 직후 클라이언트가 active_tasks +1 낙관적 업데이트
- 다음 폴링 응답으로 동기화

### 7.4 워커별 처리량 추세
- processed 카운트의 분당 변화율
- 성능 저하 즉시 인지

---

## 8. 변경 영향 범위

| 파일 | 변경 종류 | 라인 수 |
|------|---------|--------|
| `app/templates/components/global_summary.html` | UI 구조 | ±60 |
| `app/static/js/components/GlobalSummary.js` | 메서드 추가 | +30 |
| `app/templates/base.html` | 캐시 버스팅 | ±1 |
| `app/routers/dashboard_celery.py` (선택) | image 워커 매핑 | +1 |

총 추가/수정: 약 90줄 (UI 중심, 백엔드 거의 무변경)

---

## 9. 완료 기준 (Definition of Done)

- [x] 워커별 진행률이 카드 그라데이션으로 시각화됨
- [x] 진행률 % 텍스트가 active_tasks > 0일 때 표시됨
- [x] idle/busy/saturated/offline 4가지 상태 색상 구분
- [x] 호버 시 상세 툴팁 표시 (processed/concurrency/uptime)
- [x] PC + 모바일 모두 동일하게 작동
- [x] 접근성 ARIA progressbar 적용
- [x] 3초 폴링 시 부드러운 transition
- [x] 다크/라이트 테마 모두 가독성 OK
- [x] 코드 라인 < 500줄 / 함수 < 50줄 (CLAUDE.md 규칙)

---

## 10. 참고 사항

- 현재 `concurrency` 필드는 이미 백엔드 응답에 포함되어 있어 백엔드 변경 거의 없음
- Celery `inspect.stats()`의 `pool.max-concurrency` 사용 중 (`_fill_worker_stats`)
- 캐시 TTL 10초로 inspect 호출 비용 최소화 — 폴링 빈도 3초여도 부담 없음
- `--rename-command` 보안 설정과 무관 (Celery inspect는 영향 없음)

---

**문서 끝**.
사용자 검토 후 작업 진행 또는 추가 보강 사항 반영.
