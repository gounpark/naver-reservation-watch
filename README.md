# Naver Reservation Watch

네이버 예약 페이지를 주기적으로 확인하고 예약 가능 신호가 보이면 알림을 띄우는 Python 스크립트입니다.

로그인, CAPTCHA, 대기열, 결제, 최종 확정 우회는 하지 않습니다. 브라우저가 열리면 사용자가 직접 로그인하고, 예약 가능 알림 이후 남은 절차도 직접 확인해야 합니다.

내 컴퓨터가 꺼져 있어도 확인하려면 Railway 같은 원격 실행 서비스를 사용합니다. 이 경우 공개로 확인 가능한 예약 페이지에 적합하며, 매번 네이버 로그인이 필요한 페이지는 원격 실행에서 안정적으로 감시하기 어렵습니다.

## 설치

```bash
cd "../naver-reservation-watch"
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

## 실행

```bash
python3 naver_reservation_watch.py "네이버예약URL"
```

텔레그램 알림까지 같이 받으려면 환경변수를 지정합니다.

```bash
export TELEGRAM_BOT_TOKEN="텔레그램봇토큰"
export TELEGRAM_CHAT_ID="채팅ID"
python3 naver_reservation_watch.py "네이버예약URL"
```

예약 가능 시 특정 버튼을 클릭하게 하려면 selector를 지정합니다.

```bash
python3 naver_reservation_watch.py "네이버예약URL" \
  --click-selector 'button:has-text("예약하기")' \
  --interval 5
```

## 컴퓨터가 꺼져 있어도 실행하기

Railway에 이 저장소를 연결하면 `Dockerfile`을 사용해 원격 서버에서 계속 실행됩니다.

Railway 프로젝트의 Variables에 아래 값을 추가합니다.

- `RESERVATION_URL`: 감시할 네이버 예약 URL
- `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 알림을 받을 채팅 ID
- `ALERT_COOLDOWN_MINUTES`: 같은 예약 가능 상태에서 중복 알림을 막는 시간. 기본값은 `30`

실행 명령은 Dockerfile에 들어 있습니다.

```bash
python naver_reservation_watch.py --headless --no-sound --continue-after-alert
```

이렇게 실행하면 Railway 서버가 페이지를 계속 확인하고, 예약 가능 신호가 보이면 텔레그램으로 알림을 보냅니다. 알림을 보낸 뒤에도 프로세스는 종료되지 않고 계속 감시합니다.

## GitHub Actions로 가볍게 실행하기

이 저장소에는 `.github/workflows/watch.yml`도 포함되어 있어서 GitHub Actions로 5분마다 한 번씩 확인하는 방식도 사용할 수 있습니다.

GitHub 저장소의 Settings > Secrets and variables > Actions에서 아래 secrets를 추가합니다.

- `RESERVATION_URL`: 감시할 네이버 예약 URL
- `TELEGRAM_BOT_TOKEN`: 텔레그램 봇 토큰
- `TELEGRAM_CHAT_ID`: 알림을 받을 채팅 ID

바로 테스트하려면 GitHub 저장소의 Actions > Naver Reservation Watch > Run workflow를 누르면 됩니다.

## 옵션

```bash
python3 naver_reservation_watch.py --help
```
