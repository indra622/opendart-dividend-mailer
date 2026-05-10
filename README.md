# 배당 알림 메일 프로젝트

한국 상장 종목의 배당 공시를 OpenDART에서 조회해서 메일로 보내주는 도구입니다.

## 빠른 요약

- OpenDART에서 최근 배당 공시 조회
- Gmail(`gws gmail +send`)로 메일 발송
- 변동 없으면 짧게, 변동 있으면 상세 diff 표시
- 설정은 `config.json`, 비밀값은 `.env`로 분리
- 비개발자도 따라할 수 있도록 step-by-step 문서 포함

현재 기본 설정은 아래 3개 종목으로 되어 있습니다.
- 삼성전자
- SK하이닉스
- 현대차

메일은 기본적으로 다음 정보를 담아 보냅니다.
- 1주당 분배금
- 배당금총액
- 최근 공시일
- 배당기준일
- 지급예정일
- 변동 여부

또한 다음처럼 동작합니다.
- **변동이 없으면 짧은 요약 메일**을 보냅니다.
- **변동이 있으면 무엇이 바뀌었는지 자세히** 보여줍니다.
- **일부 종목 조회가 실패해도 나머지 종목은 계속 발송**합니다.

---

## 1. 이 프로젝트로 할 수 있는 것

이 도구로 할 수 있는 일:
- 원하는 종목의 배당 공시를 조회
- 최근 배당 금액을 메일로 확인
- 새 공시가 나오면 변경사항 확인
- 나중에 매일 정해진 시각에 자동 발송 설정 가능

이 도구로 지금 당장 하지 않는 일:
- 주식 매매
- 투자 판단 자동화
- 문자/카카오톡 발송

---

## 2. 준비물

시작 전에 아래 3가지를 준비하세요.

### 준비물 1) Mac 또는 Python 3가 설치된 PC
이 프로젝트는 현재 **Python 3**로 실행됩니다.

터미널에서 아래 명령으로 확인할 수 있습니다.

```bash
python3 --version
```

### 준비물 2) OpenDART API 키
배당 공시를 읽으려면 OpenDART API 키가 필요합니다.

발급처:
- <https://opendart.fss.or.kr/>

### 준비물 3) Gmail 발송이 가능한 gws 설정
이 프로젝트는 메일 발송에 `gws gmail +send`를 사용합니다.

즉, 아래가 미리 되어 있어야 합니다.
- `gws` CLI 설치
- Google 로그인/auth 완료
- Gmail 발송 가능 상태

테스트 예시:

```bash
gws gmail +send --to your-email@example.com --subject '테스트' --body '정상 동작 확인'
```

---

## 3. 설치 방법

### Step 1) 프로젝트 폴더로 이동

```bash
cd ~/codes/dart-dividend-alert
```

만약 다른 위치에 프로젝트를 두었다면 그 경로로 이동하세요.

### Step 2) 예시 파일 복사 및 확인
아래 파일들이 있는지 확인하세요.

- `dividend_alert.py`
- `config.example.json`
- `.env.example`
- `run.sh`

필요하면 예시 파일을 복사해서 시작하세요.

```bash
cp config.example.json config.json
cp .env.example .env
```

---

## 4. 설정 방법

이 프로젝트는 설정 파일을 **2개** 사용합니다.

### 4-1. `config.json`
이 파일은 **자주 바꾸는 값**을 넣는 곳입니다.

여기서 바꿀 수 있는 것:
- 메일 수신 주소 리스트
- 종목 리스트
- 메일 전송 시간
- 타임존

예시:

```json
{
  "timezone": "Asia/Seoul",
  "schedule": {
    "time": "07:30"
  },
  "email": {
    "recipients": [
      "your-email@example.com"
    ]
  },
  "stocks": [
    {
      "name": "삼성전자",
      "stock_code": "005930",
      "corp_code": "00126380"
    },
    {
      "name": "SK하이닉스",
      "stock_code": "000660",
      "corp_code": "00164779"
    },
    {
      "name": "현대차",
      "stock_code": "005380",
      "corp_code": "00164742"
    }
  ]
}
```

#### 메일 수신자 추가 방법
예를 들어 두 명에게 보내고 싶다면:

```json
"email": {
  "recipients": [
    "a@example.com",
    "b@example.com"
  ]
}
```

#### 종목 추가 방법
종목 하나를 더 추가하려면 `stocks` 배열에 한 줄 더 넣으면 됩니다.

예:

```json
{
  "name": "NAVER",
  "stock_code": "035420",
  "corp_code": "00266961"
}
```

> 주의: `corp_code`는 OpenDART용 고유번호라서, 종목코드와 다릅니다.

#### stock_code와 corp_code 찾는 방법
종목명만 알고 있다면 `stock_lookup.py`로 두 코드를 찾을 수 있습니다.
먼저 `.env`에 `OPENDART_API_KEY`가 들어 있어야 합니다.

```bash
python3 stock_lookup.py 삼성전자
```

출력 예시:

```text
검색어: 삼성전자
1. 삼성전자
   stock_code: 005930
   corp_code : 00126380
   기준일    : 20260401
```

찾은 값을 그대로 `config.json`의 `stocks`에 넣으면 됩니다.

```json
{
  "name": "삼성전자",
  "stock_code": "005930",
  "corp_code": "00126380"
}
```

참고:
- `stock_code`는 네이버증권/KRX/증권앱에서 보이는 6자리 종목코드입니다.
- `corp_code`는 OpenDART API 조회에 필요한 8자리 회사 고유번호입니다.
- `stock_lookup.py`는 OpenDART 회사고유번호 목록을 받아 `state/corp_codes.json`에 캐시합니다.
- 목록을 새로 받고 싶으면 `--refresh`를 붙여 실행하세요.

```bash
python3 stock_lookup.py 삼성전자 --refresh
```

#### 메일 전송 시간 변경 방법
예를 들어 오전 7시 30분 대신 오전 8시 45분으로 바꾸고 싶다면:

```json
"schedule": {
  "time": "08:45"
}
```

> 참고: 지금은 이 시간이 **설정값으로 저장**되며, 실제 자동 실행 등록은 나중에 별도 설정이 필요합니다.

---

### 4-2. `.env`
이 파일은 **비밀값**을 넣는 곳입니다.

예시:

```env
OPENDART_API_KEY=your_opendart_api_key
EMAIL_PROVIDER=gws_gmail_send
```

설명:
- `OPENDART_API_KEY`: OpenDART에서 발급받은 키
- `EMAIL_PROVIDER`: 현재는 `gws_gmail_send` 고정

---

## 5. 처음 실행하기

### Step 1) 테스트 모드로 실행
먼저 실제 메일을 보내지 않고, 화면에 결과만 출력해보세요.

```bash
cd ~/codes/dart-dividend-alert
python3 dividend_alert.py --print-only
```

정상이라면 아래와 비슷한 결과가 나옵니다.
- 종목별 배당 현황
- 최근 분배금
- 최근 공시일
- 현재 읽은 설정값

### Step 2) 실제 메일 보내기
출력이 정상이라면 실제 메일을 보냅니다.

```bash
cd ~/codes/dart-dividend-alert
python3 dividend_alert.py
```

또는:

```bash
cd ~/codes/dart-dividend-alert
./run.sh
```

---

## 6. 메일이 어떻게 오는지

### 6-1. 변동이 없을 때
메일이 짧게 옵니다.

예:

```text
배당 현황 - 2026-05-07 07:30

- 삼성전자: 변동 없음 / 최근 분배금 372원 / 최근 공시일 2026-04-30
- SK하이닉스: 변동 없음 / 최근 분배금 375원 / 최근 공시일 2026-04-22
- 현대차: 변동 없음 / 최근 분배금 2,500원 / 최근 공시일 2026-04-23
```

### 6-2. 변동이 있을 때
무엇이 바뀌었는지 자세히 옵니다.

예:

```text
- 삼성전자 (005930)
  - 상태: 변동 있음
  - 변경사항: 1주당 분배금: 372원 → 400원
  - 변경사항: 지급예정일: 없음 → 2026-05-29
```

### 6-3. 일부 종목이 실패할 때
나머지 종목은 정상 발송되고, 실패한 종목만 따로 표시됩니다.

예:

```text
- 현대차 (005380)
  - 상태: 조회 실패
  - 조회 결과: 실패
  - 오류: OpenDART timeout
```

---

## 7. 종목/수신자 변경하는 가장 쉬운 방법

비개발자 기준으로는 아래만 기억하면 됩니다.

### 메일 받을 사람 바꾸기
- `config.json` 열기
- `email.recipients` 수정

### 종목 바꾸기
- `config.json` 열기
- `stocks` 수정

### 시간 바꾸기
- `config.json` 열기
- `schedule.time` 수정

### 비밀키 바꾸기
- `.env` 열기
- `OPENDART_API_KEY` 수정

즉:
- **설정값은 `config.json`**
- **비밀값은 `.env`**

이렇게만 기억하면 됩니다.

> GitHub에 올릴 때는 실제 운영용 `config.json`과 `.env`에 개인 정보나 비밀 키가 남아 있지 않은지 꼭 확인하세요.

---

## 8. 테스트 방법

이 프로젝트에는 테스트 코드가 들어 있습니다.

실행:

```bash
cd ~/codes/dart-dividend-alert
python3 -m unittest -v
```

현재 테스트하는 내용:
- 배당 데이터 파싱
- 상태 비교
- 변경 diff 표시
- 설정 파일 로딩
- 상태 파일 저장/복원
- 실제 공시 fixture 기반 검증
- 설정 변경 반영 검증

---

## 9. 자주 생길 수 있는 문제

### 문제 1) `Missing required env: OPENDART_API_KEY`
원인:
- `.env` 파일에 키가 없거나 비어 있음

해결:
- `.env` 열기
- `OPENDART_API_KEY=...` 확인

### 문제 2) 메일이 안 보내짐
원인:
- `gws` 로그인/auth가 안 되어 있음
- Gmail 발송 권한 문제

해결:
- `gws` 로그인 상태 확인
- 테스트 메일을 직접 보내보기

```bash
gws gmail +send --to your-email@example.com --subject '테스트' --body '정상 동작 확인'
```

### 문제 3) 종목 추가했는데 조회 실패
원인:
- `corp_code`가 잘못됨
- 종목명이 비슷한 다른 회사의 코드를 입력함

해결:
- 아래 명령으로 `stock_code`와 `corp_code`를 다시 확인

```bash
python3 stock_lookup.py 종목명 --refresh
```

### 문제 4) 출력은 되는데 자동 발송이 안 됨
원인:
- 아직 자동 실행 스케줄을 등록하지 않았음

해결:
- 나중에 cron 또는 launchd 등록 필요

---

## 10. 파일 설명

- `dividend_alert.py` : 메인 실행 파일
- `stock_lookup.py` : 종목명으로 `stock_code`와 OpenDART `corp_code`를 찾는 도구
- `run.sh` : 실행 편의용 스크립트
- `config.json` : 사용자 설정 파일
- `config.example.json` : 설정 예시 파일
- `.env` : 비밀값 파일
- `state/latest.json` : 마지막 조회 상태 저장 파일
- `tests/fixtures/` : 실제 공시 샘플 파일
- `test_dividend_alert.py` : 테스트 코드

---

## 11. 현재 권장 사용 순서

처음 쓰는 사람이라면 아래 순서대로 하면 됩니다.

1. `config.json` 수정
2. `.env`에 OpenDART 키 입력
3. `python3 dividend_alert.py --print-only` 실행
4. 결과가 맞는지 확인
5. `python3 dividend_alert.py` 실행
6. 메일 수신 확인
7. 나중에 원하면 자동 실행 등록

---

## 12. 현재 상태

현재 구현된 기능:
- OpenDART 배당 공시 조회
- 최근 분배금 추출
- 변동 여부 판정
- 상세 diff 표시
- 변동 없을 때 compact 메일 출력
- 일부 종목 실패 허용
- 설정 파일 분리
- 테스트 코드 포함

현재 자동 실행 등록은 아직 별도 설정 단계이며,
실제 스케줄 등록은 필요 시 cron 또는 launchd로 추가하면 됩니다.

---

## 13. GitHub에 올리기 전 체크리스트

- `config.json`이 예시값인지 확인
- `.env`가 커밋되지 않았는지 확인
- OpenDART API 키가 코드나 문서에 직접 적혀 있지 않은지 확인
- 메일 주소가 공개되어도 되는 값인지 확인
- `python3 -m unittest -v` 테스트 통과 확인
- `python3 dividend_alert.py --print-only` 실행 확인
