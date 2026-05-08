# 구현 스펙

## 대상 종목

기본값은 아래 3개지만, 실제 운영값은 `config.json`에서 변경 가능하다.

- 삼성전자 / 005930
- SK하이닉스 / 000660
- 현대차 / 005380

## 원하는 결과

매일 07:30 기준으로 종목별 배당 현황을 간단히 요약한다.

### 기본 메시지

배당 현황 - YYYY-MM-DD 07:30
- 삼성전자: 변동 없음
- SK하이닉스: 변동 없음
- 현대차: 변동 없음

### 변동이 있을 때

배당 현황 - YYYY-MM-DD 07:30
- 삼성전자: 최근 배당 관련 공시 확인
  - 공시명: 현금ㆍ현물배당결정
  - 공시일: YYYY-MM-DD
  - 주당 배당금: N원
  - 기준일: YYYY-MM-DD
  - 지급일: YYYY-MM-DD
- SK하이닉스: 변동 없음
- 현대차: 변동 없음

## OpenDART 조회 전략

### 1) corp_code 확보
OpenDART는 stock code가 아니라 corp_code를 주로 사용한다.
따라서 최초 1회 `corpCode.xml`을 내려받아 아래 매핑을 저장한다.

- 005930 -> 삼성전자 -> corp_code
- 000660 -> SK하이닉스 -> corp_code
- 005380 -> 현대차 -> corp_code

### 2) 최근 공시 목록 조회
종목별 최근 공시를 조회한 뒤 다음 조건에 맞는 공시를 우선 탐색한다.

- 공시명에 `배당`
- 공시명에 `현금ㆍ현물배당결정`
- 필요 시 사업보고서/분기보고서 내부 배당 항목 추적

### 3) 구조화
최소 아래 필드를 뽑는다.

- companyName
- stockCode
- disclosureTitle
- disclosureDate
- dividendPerShare
- recordDate
- paymentDate
- note

### 4) 메시지 정책
- 변동이 없으면 짧게
- 신규 공시가 있으면 자세히
- API 에러 시 실패 사실을 숨기지 말고 간단히 표시

예:
- SK하이닉스: 조회 실패 (OpenDART 응답 오류)

## 스케줄링

### 옵션 A: cron
`30 7 * * *`

### 옵션 B: launchd
macOS에서 안정적으로 돌릴 경우 launchd plist 사용 가능.

## 메일 발송

초기 구현은 Gmail SMTP를 우선 고려한다.

필수 정보:
- 수신자 목록: `config.json`의 `email.recipients`
- 발송 시각: `config.json`의 `schedule.time`
- 종목 목록: `config.json`의 `stocks`

메일 제목 예시:
- `[배당 알림] 2026-05-07 삼성전자/SK하이닉스/현대차`

## 구현 메모

- 현재 단계에서는 이메일 발송이 목표
- Gmail API보다 SMTP+앱 비밀번호가 구현이 단순함
- OpenDART API 키는 사용자 제공 필요
- Gmail 발송 자격증명은 사용자 제공 필요
