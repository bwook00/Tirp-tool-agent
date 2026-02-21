# 배포 가이드 (비개발자용)

이 문서는 Tirp-tool-agent를 **Railway**에 배포하고, **Tally.so** 설문과 연결하는 전체 과정을 설명합니다.
컴퓨터에 Docker나 프로그래밍 도구를 설치할 필요 없이, 웹 브라우저만으로 진행할 수 있습니다.

---

## 목차

1. [GitHub 계정 만들기](#1-github-계정-만들기)
2. [이 프로젝트 Fork하기](#2-이-프로젝트-fork하기)
3. [Railway 계정 만들기](#3-railway-계정-만들기)
4. [Railway에서 배포하기](#4-railway에서-배포하기)
5. [공개 URL 생성하기](#5-공개-url-생성하기)
6. [Tally 웹훅 연결하기](#6-tally-웹훅-연결하기)
7. [Tally 리다이렉트 설정하기](#7-tally-리다이렉트-설정하기)
8. [테스트하기](#8-테스트하기)
9. [문제 해결](#9-문제-해결)

---

## 1. GitHub 계정 만들기

> 이미 GitHub 계정이 있다면 [2단계](#2-이-프로젝트-fork하기)로 건너뛰세요.

1. **https://github.com/signup** 에 접속합니다.
2. 이메일 주소를 입력합니다.
3. 비밀번호를 설정합니다.
4. 사용자 이름(username)을 정합니다.
5. 보안 퍼즐을 풀고 **Create account**를 클릭합니다.
6. 이메일로 온 **인증 코드**를 입력합니다.

---

## 2. 이 프로젝트 Fork하기

Fork는 원본 프로젝트를 내 GitHub 계정에 복사하는 것입니다.

1. **https://github.com/bwook00/Tirp-tool-agent** 에 접속합니다.
2. 오른쪽 위의 **Fork** 버튼을 클릭합니다.
3. "Create fork"를 클릭합니다.
4. 잠시 후, `https://github.com/{내 username}/Tirp-tool-agent` 주소로 내 복사본이 생깁니다.

---

## 3. Railway 계정 만들기

Railway는 웹 서비스를 쉽게 배포할 수 있는 클라우드 플랫폼입니다.
가입 시 신용카드가 필요 없으며, 무료 크레딧 $5가 제공됩니다.

1. **https://railway.com** 에 접속합니다.
2. 오른쪽 위의 **Login**을 클릭합니다.
3. **Login with GitHub**를 선택합니다.
4. GitHub 로그인 후, Railway가 GitHub 접근 권한을 요청하면 **Authorize**를 클릭합니다.
5. 가입 완료! 대시보드 화면이 나타납니다.

### Railway 무료 요금제

| 항목 | 내용 |
|------|------|
| 최초 무료 크레딧 | $5 (일회성) |
| 이후 월 무료 크레딧 | $1/월 |
| 신용카드 필요 | 아니오 |
| RAM | 512MB (무료) / 1GB (Trial) |

> 이 프로젝트는 무료 요금제로 충분히 운영할 수 있습니다.

---

## 4. Railway에서 배포하기

### 4-1. 새 프로젝트 만들기

1. Railway 대시보드에서 **New Project**를 클릭합니다.
2. **Deploy from GitHub repo**를 선택합니다.
3. 처음이라면 **Configure GitHub App** 버튼이 나타납니다:
   - 클릭하면 GitHub 페이지로 이동합니다.
   - **Only select repositories**를 선택하고, `Tirp-tool-agent`를 찾아 체크합니다.
   - **Install & Authorize**를 클릭합니다.
4. 목록에서 **Tirp-tool-agent**를 선택합니다.
5. **Deploy Now**를 클릭합니다.

Railway가 자동으로 Dockerfile을 감지하고 빌드를 시작합니다.
빌드에 3~5분 정도 걸립니다. 화면에 로그가 표시됩니다.

### 4-2. 환경 변수 설정하기

> 이 단계는 선택사항입니다. 환경 변수 없이도 기본 동작합니다.
> Tally 웹훅 서명 검증을 사용하려면 설정하세요.

1. 배포된 서비스 카드를 클릭합니다.
2. 상단의 **Variables** 탭을 클릭합니다.
3. **New Variable**를 클릭하여 아래 변수를 추가합니다:

| 변수 이름 | 값 | 필수 여부 | 설명 |
|-----------|-----|-----------|------|
| `TALLY_SIGNING_SECRET` | Tally에서 발급받은 시크릿 | 선택 | 웹훅 서명 검증용 |

> **API 키가 필요 없습니다!** 교통편 검색은 무료 HAFAS API(DB transport.rest)를 사용합니다.

4. 변수 추가 후 Railway가 자동으로 재배포합니다.

---

## 5. 공개 URL 생성하기

기본적으로 Railway 서비스는 외부에서 접속할 수 없습니다.
공개 URL을 만들어야 합니다.

1. 배포된 서비스 카드를 클릭합니다.
2. 상단의 **Settings** 탭을 클릭합니다.
3. 아래로 스크롤하여 **Networking** 섹션을 찾습니다.
4. **Generate Domain**을 클릭합니다.
5. `xxxxx.up.railway.app` 형태의 URL이 생성됩니다.

이 URL을 메모해 두세요. 다음 단계에서 필요합니다.

### 배포 확인

브라우저에서 아래 URL에 접속해서 확인합니다:

```
https://xxxxx.up.railway.app/health
```

`{"status": "ok"}` 이 나타나면 배포가 성공한 것입니다.

---

## 6. Tally 웹훅 연결하기

Tally 설문이 제출되면, 자동으로 우리 서버에 데이터를 보내도록 설정합니다.

1. **https://tally.so** 에 로그인합니다.
2. 연결할 설문 폼을 엽니다.
3. 상단의 **Integrations** 탭을 클릭합니다.
4. **Webhooks** 항목에서 **Connect**를 클릭합니다.
5. **Endpoint URL**에 아래 형식으로 입력합니다:

```
https://xxxxx.up.railway.app/webhook/tally
```

> `xxxxx.up.railway.app` 부분을 5단계에서 생성한 실제 URL로 바꿔주세요.

6. (선택) **Signing secret**을 설정하면 보안이 강화됩니다:
   - 시크릿 값을 입력합니다 (아무 문자열이나 가능).
   - 같은 값을 Railway 환경 변수 `TALLY_SIGNING_SECRET`에도 설정합니다.
7. **Save**를 클릭합니다.

---

## 7. Tally 리다이렉트 설정하기

설문 제출 후 사용자를 대기 화면으로 보냅니다.

1. Tally 폼 편집 화면에서 **Settings** (톱니바퀴 아이콘)를 클릭합니다.
2. **After submission** 섹션을 찾습니다.
3. **Redirect to URL**을 선택합니다.
4. 아래 URL을 입력합니다:

```
https://xxxxx.up.railway.app/wait
```

> `xxxxx.up.railway.app` 부분을 실제 URL로 바꿔주세요.

5. **Save**를 클릭합니다.

---

## 8. 테스트하기

모든 설정이 끝났습니다! 이제 실제로 테스트해봅니다.

### 8-1. 설문 제출

1. Tally 설문 링크를 엽니다.
2. 아래 정보를 입력합니다:
   - 출발지: `Paris` (유럽 도시)
   - 도착지: `Berlin` (유럽 도시)
   - 출발 날짜: 내일 이후의 날짜
3. 설문을 제출합니다.

### 8-2. 대기 화면 확인

설문 제출 후 자동으로 대기 화면(`/wait`)으로 이동합니다.
화면에 "최적의 교통편을 찾고 있습니다" 메시지가 표시됩니다.

### 8-3. 결과 확인

처리가 완료되면 자동으로 결과 화면(`/r/{result_id}`)으로 이동합니다.
추천된 교통편 정보(열차/버스, 가격, 소요시간 등)가 표시됩니다.

> 처리에 보통 10~30초 정도 걸립니다. 최대 3분까지 기다려주세요.

---

## 9. 문제 해결

### "최적의 교통편을 찾고 있습니다"에서 멈추는 경우

- Railway 로그를 확인합니다:
  1. Railway 대시보드에서 서비스 클릭
  2. **Deployments** 탭에서 최신 배포 클릭
  3. **View Logs**로 로그 확인
- 유럽 도시 이름을 영어로 입력했는지 확인합니다 (예: Paris, Berlin, Munich)

### /health 가 응답하지 않는 경우

- 배포가 완료될 때까지 기다립니다 (3~5분 소요).
- Railway 대시보드에서 빌드 로그를 확인합니다. 빌드 실패 시 빨간색으로 표시됩니다.
- **Generate Domain**을 했는지 확인합니다 (5단계).

### 설문 제출 후 아무 반응이 없는 경우

- Tally 웹훅 설정이 올바른지 확인합니다:
  1. Tally 폼 편집 > Integrations > Webhooks
  2. Endpoint URL이 `https://xxxxx.up.railway.app/webhook/tally` 형식인지 확인
  3. 시계 아이콘을 클릭하면 웹훅 전송 기록을 볼 수 있습니다
- Tally 리다이렉트 URL이 맞는지 확인합니다 (7단계).

### 무료 크레딧이 소진된 경우

- Railway 무료 플랜은 월 $1 크레딧을 제공합니다.
- 사용량이 많아지면 Hobby 플랜($5/월)으로 업그레이드하세요.
- Railway 대시보드 > **Settings** > **Billing**에서 확인할 수 있습니다.

---

## 요약: 전체 설정에 필요한 URL

| 용도 | URL |
|------|-----|
| GitHub 가입 | https://github.com/signup |
| 프로젝트 원본 | https://github.com/bwook00/Tirp-tool-agent |
| Railway 가입 | https://railway.com |
| Railway 대시보드 | https://railway.com/dashboard |
| Tally 대시보드 | https://tally.so |
| 웹훅 URL | `https://{내 도메인}.up.railway.app/webhook/tally` |
| 리다이렉트 URL | `https://{내 도메인}.up.railway.app/wait` |
| 헬스체크 | `https://{내 도메인}.up.railway.app/health` |
