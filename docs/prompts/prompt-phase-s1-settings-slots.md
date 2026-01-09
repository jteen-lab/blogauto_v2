# Phase S-1: 설정 시스템 및 구글 블로거 슬롯 관리

## 📋 개요

대시보드 요약탭에 설정 기능을 추가하고, 구글 블로거의 시간대별 발행 제한을 관리하는 슬롯 시스템을 구현합니다.

---

## 🎯 목표

1. **설정 시스템**: 계정/AI/API 설정을 관리하는 통합 설정 팝업
2. **슬롯 관리**: 구글 블로거 시간대별 발행 제한 검증 및 시각화

---

## Part 1: 설정 시스템

### 1-1. 대시보드 요약탭에 설정 아이콘 추가

**위치**: 요약탭 우측, 확장 버튼(▼) 옆

```html
<!-- 현재 -->
<div class="flex items-center gap-3">
    <!-- 4개 지표 카드 -->
    <button @click="togglePanel()">▼</button>
</div>

<!-- 변경 후 -->
<div class="flex items-center gap-3">
    <!-- 4개 지표 카드 -->
    <button @click="openSettings()" class="p-2 hover:bg-gray-200 rounded-lg">
        <svg><!-- 톱니바퀴 아이콘 --></svg>
    </button>
    <button @click="togglePanel()">▼</button>
</div>
```

### 1-2. 설정 팝업 UI

**스타일**: 모듈 관리 팝업과 동일한 중앙 팝업 스타일

```
┌─────────────────────────────────────────────────────────────┐
│                        ⚙️ 설정                         [X] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [계정 설정]  [AI 서비스]  [API 설정]    ← 탭 UI            │
│  ─────────────────────────────────────                      │
│                                                             │
│  (각 탭 내용)                                               │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                              [취소]  [저장]                 │
└─────────────────────────────────────────────────────────────┘
```

### 1-3. 탭별 내용

#### 탭 1: 계정 설정
```
- 사용자 이름 (읽기 전용)
- 이메일 (읽기 전용)
- 비밀번호 변경 버튼
```

#### 탭 2: AI 서비스 설정
```
- OpenAI API 키 입력 (password 타입)
- Claude API 키 입력 (password 타입)
- 기본 AI 모델 선택 (select)
  - GPT-4
  - GPT-3.5
  - Claude 3.5 Sonnet
```

#### 탭 3: API 설정
```
- Google Blogger 시간당 발행 제한
  - select: 2회 / 3회 / 4회
  - 기본값: 2회
  
- 3회 이상 선택 시 경고 메시지 표시:
  ┌─────────────────────────────────────────────────────┐
  │ ⚠️ 주의                                             │
  │ 잦은 빈도로 API를 사용할 경우 Google 계정이         │
  │ 제한될 수 있습니다. 신중하게 설정하세요.            │
  └─────────────────────────────────────────────────────┘
```

### 1-4. 데이터베이스

**user_settings 테이블 (신규)**

```sql
CREATE TABLE user_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    
    -- AI 설정
    openai_api_key VARCHAR(255),
    claude_api_key VARCHAR(255),
    default_ai_model VARCHAR(50) DEFAULT 'gpt-4',
    
    -- API 설정
    blogger_hourly_limit INTEGER DEFAULT 2 CHECK (blogger_hourly_limit BETWEEN 2 AND 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 1-5. API 엔드포인트

```python
# app/routers/settings.py

GET  /api/v1/settings          # 현재 설정 조회
PUT  /api/v1/settings          # 설정 저장
POST /api/v1/settings/password # 비밀번호 변경
```

---

## Part 2: 구글 블로거 슬롯 관리

### 2-1. 핵심 개념

```
동일 Google 계정 내에서:
- 같은 시간대(요일+시간)에 블로거 발행 제한
- 제한 횟수: 사용자 설정값 (2~4회)
- 제한 초과 시: 등록 차단 (강제)
```

### 2-2. 슬롯 테이블 (신규)

```sql
CREATE TABLE blogger_time_slots (
    id SERIAL PRIMARY KEY,
    google_credential_id INTEGER NOT NULL REFERENCES google_credentials(id) ON DELETE CASCADE,
    blog_id INTEGER NOT NULL REFERENCES blogs(id) ON DELETE CASCADE,
    flow_id INTEGER NOT NULL REFERENCES flows(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),  -- 0=월 ~ 6=일
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(google_credential_id, blog_id, flow_id, day_of_week, hour)
);

CREATE INDEX idx_slots_credential_time ON blogger_time_slots(google_credential_id, day_of_week, hour);
```

### 2-3. 슬롯 검증 로직

```python
# app/services/slot_validator.py

class SlotValidator:
    """구글 블로거 시간대 슬롯 검증"""
    
    async def get_slot_status(
        self,
        google_credential_id: int,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, List[int]]:
        """
        해당 Google 계정의 모든 시간대별 사용 현황 조회
        
        Returns:
            {
                "0-9": 2,   # 월요일 9시: 2개 등록됨
                "0-10": 1,  # 월요일 10시: 1개 등록됨
                ...
            }
        """
    
    async def validate_schedule(
        self,
        google_credential_id: int,
        schedule_matrix: List[List[bool]],
        user_limit: int,
        exclude_flow_id: Optional[int] = None,
        db: AsyncSession
    ) -> ValidationResult:
        """
        스케줄 매트릭스 검증
        
        Args:
            google_credential_id: 구글 계정 ID
            schedule_matrix: 7x24 스케줄 매트릭스
            user_limit: 사용자 설정 제한값 (2~4)
            exclude_flow_id: 제외할 플로우 ID (수정 시)
        
        Returns:
            ValidationResult:
                - is_valid: 전체 유효 여부
                - conflicts: 충돌 시간대 목록 [(day, hour), ...]
        """
    
    async def reserve_slots(
        self,
        google_credential_id: int,
        blog_id: int,
        flow_id: int,
        schedule_matrix: List[List[bool]],
        db: AsyncSession
    ) -> bool:
        """슬롯 예약 (플로우에 블로거 등록 시)"""
    
    async def release_slots(
        self,
        blog_id: int,
        flow_id: int,
        db: AsyncSession
    ) -> int:
        """슬롯 해제 (플로우에서 블로거 제거 시)"""
```

### 2-4. API 엔드포인트

```python
# app/routers/slots.py

GET /api/v1/slots/status/{google_credential_id}
# 해당 Google 계정의 시간대별 슬롯 사용 현황

POST /api/v1/slots/validate
# 스케줄 매트릭스 검증
# Body: { google_credential_id, schedule_matrix, exclude_flow_id? }
# Response: { is_valid, conflicts: [[day, hour], ...] }
```

### 2-5. 스케줄 매트릭스 UI 수정

**색상 체계**

| 색상 | 클래스 | 의미 | 동작 |
|------|--------|------|------|
| 🔵 파란색 | `bg-blue-500` | 현재 선택 (등록 가능) | 클릭 가능 |
| 🟠 주황색 | `bg-orange-500` | 시간대 중복 (제한 초과) | **클릭 불가** |
| ⬜ 흰색 | `bg-white` | 미선택 | 클릭 가능 |

**구현**

```javascript
// app/static/js/flows/schedule-matrix.js

function getSlotColor(day, hour, isSelected, slotStatus, userLimit) {
    const key = `${day}-${hour}`;
    const currentCount = slotStatus[key] || 0;
    
    if (isSelected) {
        // 이미 선택된 상태
        if (currentCount >= userLimit) {
            return 'bg-orange-500';  // 중복 (제한 초과)
        }
        return 'bg-blue-500';  // 정상 선택
    }
    
    // 미선택 상태에서 클릭 시
    if (currentCount >= userLimit) {
        return 'bg-orange-200';  // 선택 불가 표시
    }
    return 'bg-white';  // 선택 가능
}

function canSelectSlot(day, hour, slotStatus, userLimit) {
    const key = `${day}-${hour}`;
    const currentCount = slotStatus[key] || 0;
    return currentCount < userLimit;
}
```

**HTML 템플릿**

```html
<!-- 스케줄 매트릭스 하단 안내 -->
<div class="mt-4 p-3 bg-gray-50 rounded-lg text-sm">
    <div class="flex items-center gap-4">
        <div class="flex items-center gap-2">
            <span class="w-4 h-4 bg-blue-500 rounded"></span>
            <span>선택됨</span>
        </div>
        <div class="flex items-center gap-2">
            <span class="w-4 h-4 bg-orange-500 rounded"></span>
            <span>중복 (등록 불가)</span>
        </div>
    </div>
    <p x-show="hasConflicts" class="mt-2 text-red-600">
        🟠 주황색 시간대를 해제해야 블로거를 등록할 수 있습니다
    </p>
</div>
```

### 2-6. 플로우 블로거 등록 시 검증 흐름

```
1. 블로거 추가 버튼 클릭
   ↓
2. 해당 블로거의 Google 계정 확인
   ↓
3. API 호출: GET /api/v1/slots/status/{google_credential_id}
   ↓
4. 스케줄 매트릭스에 현재 슬롯 상태 반영
   - 제한 초과 시간대: 주황색 표시
   ↓
5. 사용자가 스케줄 선택
   - 주황색 셀: 클릭 불가
   ↓
6. 등록 버튼 클릭
   ↓
7. API 호출: POST /api/v1/slots/validate
   ↓
8. 검증 통과 시 → 블로거 등록 + 슬롯 예약
   검증 실패 시 → 에러 메시지 표시
```

---

## Part 3: 파일 구조

```
services/republish/app/
├── models/
│   ├── user_settings.py       # 신규: 사용자 설정 모델
│   └── blogger_time_slot.py   # 신규: 슬롯 모델
│
├── schemas/
│   ├── settings.py            # 신규: 설정 스키마
│   └── slot.py                # 신규: 슬롯 스키마
│
├── services/
│   └── slot_validator.py      # 신규: 슬롯 검증 서비스
│
├── routers/
│   ├── settings.py            # 신규: 설정 API
│   └── slots.py               # 신규: 슬롯 API
│
├── templates/
│   ├── base.html              # 수정: 요약탭에 ⚙️ 아이콘 추가
│   ├── settings/
│   │   └── modal.html         # 신규: 설정 팝업
│   └── flows/
│       └── _form.html         # 수정: 스케줄 매트릭스 색상
│
└── static/js/
    ├── settings.js            # 신규: 설정 팝업 JS
    └── flows/
        └── schedule-matrix.js # 신규: 스케줄 색상 로직
```

---

## Part 4: 구현 순서

### Phase 1: 설정 시스템 (우선)
1. user_settings 테이블 생성
2. UserSettings 모델 작성
3. settings API 작성
4. 대시보드 요약탭에 ⚙️ 아이콘 추가
5. 설정 팝업 UI 작성
6. API 설정 탭 (시간당 발행 제한)

### Phase 2: 슬롯 관리 시스템
1. blogger_time_slots 테이블 생성
2. BloggerTimeSlot 모델 작성
3. SlotValidator 서비스 작성
4. slots API 작성
5. 스케줄 매트릭스 색상 표시 수정
6. 플로우 블로거 등록 시 검증 연동

---

## 🧪 테스트 시나리오

### 설정 테스트
| # | 시나리오 | 예상 결과 |
|---|----------|----------|
| 1 | ⚙️ 아이콘 클릭 | 설정 팝업 열림 |
| 2 | API 설정 탭에서 3회 선택 | 경고 메시지 표시 |
| 3 | 설정 저장 | DB 저장 + 팝업 닫힘 |

### 슬롯 테스트 (제한 2회 기준)
| # | 시나리오 | 예상 결과 |
|---|----------|----------|
| 1 | 빈 시간대에 블로거 등록 | 🔵 파란색, 등록 성공 |
| 2 | 1개 등록된 시간대에 추가 | 🔵 파란색, 등록 성공 |
| 3 | 2개 등록된 시간대에 추가 시도 | 🟠 주황색, 클릭 불가 |
| 4 | 주황색 시간대 있는 상태로 등록 시도 | 등록 버튼 비활성화 |

---

## ⚠️ 제약사항

- 파일당 300줄 미만
- 함수당 50줄 미만
- 타입 힌트 필수
- Docstring 필수
- 에러 처리 필수

---

위 내용대로 구현해주세요. Phase 1 (설정 시스템)부터 시작합니다.
