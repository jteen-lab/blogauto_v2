# BlogAuto 설치 메뉴얼 — Oracle Cloud 무료 인스턴스

> **대상**: 컴퓨터에 익숙하지 않은 사용자 / **소요 시간**: 약 30~40분

---

## 0. 한눈에 보는 전체 흐름

```
1) Oracle 클라우드 가입 (10분)
       ↓
2) 무료 VM 만들기 (10분)
       ↓
3) (선택) DuckDNS 도메인 연결 (5분)
       ↓
4) SSH로 서버 접속 (5분)
       ↓
5) 설치 명령 한 줄 실행 (10분, 자동)
       ↓
6) 브라우저로 접속 ✨
```

---

## 1. Oracle Cloud 가입 (10분)

1. https://www.oracle.com/cloud/free 접속 → **Start for free** 클릭
2. 이메일/이름 입력 → 인증 메일 확인
3. 신용카드 등록 (요금 부과 없음. 본인 인증용)
4. 지역 선택 — **Seoul** 또는 **Tokyo** 권장 (한국에서 가까움)

---

## 2. 무료 VM 만들기 (10분)

1. 콘솔 로그인 → **Compute** → **Instances** → **Create Instance**
2. 다음 옵션으로 설정:
   - **Name**: `blogauto-server` (원하는 이름)
   - **Image**: `Canonical Ubuntu 22.04`
   - **Shape**: `VM.Standard.E2.1.Micro` (Always Free)
   - **Networking**: 기본값 그대로
   - **SSH keys**: **Generate SSH key pair** 선택 → **Save private key** 클릭 (절대 잃어버리면 안 됨)
3. **Create** 클릭 → 1~2분 대기 → **Running** 상태 확인
4. **공인 IP 주소(Public IP)** 복사 (예: `132.145.99.10`) — 메모해 둘 것

**방화벽 설정** (필수):
1. Instance 화면 → **Subnet** 클릭 → **Default Security List**
2. **Add Ingress Rules**로 다음 포트 열기:
   - Source CIDR: `0.0.0.0/0`, Port: `80` (HTTP)
   - Source CIDR: `0.0.0.0/0`, Port: `443` (HTTPS)
   - Source CIDR: `0.0.0.0/0`, Port: `22` 는 보통 이미 열려있음

---

## 3. (선택) DuckDNS 도메인 연결 (5분)

도메인 없이도 IP로 사용 가능하지만, HTTPS 자물쇠 보안을 원하면 권장.

1. https://www.duckdns.org → Google/GitHub로 로그인
2. **Add domain**: 원하는 이름 입력 (예: `my-blogauto`)
   → 결과 주소: `my-blogauto.duckdns.org`
3. 같은 줄의 **current ip** 칸에 위에서 받은 Oracle IP 입력 → **update ip**
4. 도메인 ↔ IP 연결 완료

(IP가 바뀌어도 DuckDNS 자동 갱신을 원하면 메뉴얼 별첨 참조 — 일반적으로 Oracle 무료 IP는 잘 안 바뀜)

---

## 4. SSH로 서버 접속 (5분)

### 윈도우 사용자
1. **PowerShell** 실행 (시작 → "powershell" 검색)
2. 다운로드 받은 SSH 키 파일(예: `ssh-key.key`)이 있는 폴더로 이동:
   ```powershell
   cd C:\Users\본인이름\Downloads
   ```
3. 키 파일 권한 조정 (윈도우는 한 번 필요):
   ```powershell
   icacls ssh-key.key /inheritance:r /grant:r "%username%:R"
   ```
4. 접속:
   ```powershell
   ssh -i ssh-key.key ubuntu@본인의IP
   ```
5. `yes` 입력 → 접속 완료

### 맥 사용자
1. **터미널** 실행
2. 키 파일 권한:
   ```bash
   chmod 400 ~/Downloads/ssh-key.key
   ```
3. 접속:
   ```bash
   ssh -i ~/Downloads/ssh-key.key ubuntu@본인의IP
   ```

> 💡 접속 후 명령 프롬프트가 `ubuntu@blogauto-server:~$` 같이 바뀌면 성공

---

## 5. 설치 명령 한 줄 (10분)

서버에 접속한 상태에서 아래 명령 **딱 한 줄**:

```bash
curl -fsSL https://jteen-lab.github.io/blogauto-deploy/install.sh | bash
```

이후 마법사가 6가지 묻습니다:
1. **Gmail 주소** (메일 발송용) — 본인 Gmail 입력
2. **Gmail 앱 비밀번호** — `https://myaccount.google.com/apppasswords` 에서 발급한 16자
3. **도메인** — 위 3번에서 만든 `my-blogauto.duckdns.org` 또는 그냥 엔터 (IP 사용)
4. **관리자 이메일** — BlogAuto 로그인용
5. **관리자 비밀번호** — 8자 이상
6. **자동 업데이트** — `Y` 권장

자동 진행: 5~10분 (이미지 다운로드)

---

## 6. 브라우저로 접속

설치 완료 메시지의 URL로 접속:
- 도메인 있는 경우: `https://my-blogauto.duckdns.org`
- IP만 있는 경우: `http://132.145.99.10`

처음 화면에서 마법사에 입력한 관리자 이메일/비밀번호로 로그인.

---

## 7. 자주 쓰는 명령

```bash
blogauto status      # 상태 확인
blogauto logs        # 로그 보기 (q로 종료)
blogauto restart     # 재시작
blogauto backup      # 데이터 백업
blogauto update      # 수동 업데이트
blogauto rollback    # 이전 버전 복귀
```

---

## 8. 문제 해결

| 증상 | 해결 |
|------|------|
| SSH 접속 안 됨 | 1) 방화벽 22번 열려있는지, 2) 키 파일 권한, 3) Public IP 정확한지 |
| 설치 도중 멈춤 | `Ctrl+C`로 취소 후 다시 실행 (이미 받은 건 재사용됨) |
| 브라우저 "안전하지 않음" 경고 | 도메인 없으면 정상 (HTTPS 인증서는 도메인 필수) |
| 메일 발송 실패 | Gmail 2단계 인증 켰는지, 앱 비밀번호 정확한지 확인 |
| 디스크 부족 | `blogauto backup` 후 오래된 백업 삭제, 또는 인스턴스 디스크 추가 |
| 컨테이너 죽음 | `blogauto logs app` 로 에러 확인 후 `blogauto restart` |

---

## 9. 정기 점검 권장

월 1회:
- `blogauto backup` — 백업 파일을 PC로 다운로드 (`scp`)
- Oracle 콘솔에서 인스턴스 정상 동작 확인

---

**메뉴얼 끝**.
