#!/usr/bin/env python3
"""
Watch a Naver Booking page and alert when reservation availability appears.

This script does not bypass login, CAPTCHA, queues, payments, or final
confirmation. Log in manually in the opened browser, then leave the script
running until availability appears.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TYPE_CHECKING
from urllib.parse import urlencode
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from playwright.sync_api import Page

try:
    from playwright.sync_api import Error, TimeoutError, sync_playwright
except ModuleNotFoundError:
    Error = Exception
    TimeoutError = TimeoutError
    sync_playwright = None


DEFAULT_AVAILABLE_TEXT = (
    "예약하기",
    "예약 가능",
    "신청하기",
    "예매하기",
)
DEFAULT_UNAVAILABLE_TEXT = (
    "예약마감",
    "마감",
    "매진",
    "예약불가",
    "예약 불가",
    "준비중",
    "오픈예정",
)


@dataclass(frozen=True)
class WatchConfig:
    url: str
    profile_dir: Path
    interval_seconds: float
    timeout_minutes: float | None
    available_text: tuple[str, ...]
    unavailable_text: tuple[str, ...]
    click_selector: str | None
    headless: bool
    sound: bool
    once: bool
    continue_after_alert: bool
    alert_cooldown_minutes: float
    telegram_bot_token: str | None
    telegram_chat_id: str | None


def parse_csv(values: str | None, defaults: Iterable[str]) -> tuple[str, ...]:
    if not values:
        return tuple(defaults)
    parsed = tuple(item.strip() for item in values.split(",") if item.strip())
    return parsed or tuple(defaults)


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "false",
        }
    ).encode()
    request = Request(api_url, data=payload, method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except OSError as exc:
        print(f"텔레그램 알림 전송 실패: {exc}", file=sys.stderr)
        return False


def notify(title: str, message: str, config: WatchConfig) -> None:
    if config.telegram_bot_token and config.telegram_chat_id:
        telegram_message = f"{title}\n{message}\n{config.url}"
        if send_telegram(config.telegram_bot_token, config.telegram_chat_id, telegram_message):
            print("텔레그램 알림을 보냈습니다.")

    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            check=False,
        )
        if config.sound:
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
    else:
        if config.sound:
            print("\a", end="", flush=True)


def compile_text_pattern(words: tuple[str, ...]) -> re.Pattern[str]:
    escaped = [re.escape(word) for word in words if word]
    return re.compile("|".join(escaped), re.IGNORECASE)


def visible_text(page: "Page") -> str:
    return page.locator("body").inner_text(timeout=5_000)


def has_enabled_click_target(page: "Page", selector: str) -> bool:
    targets = page.locator(selector)
    for index in range(targets.count()):
        target = targets.nth(index)
        try:
            if target.is_visible(timeout=500) and target.is_enabled(timeout=500):
                return True
        except Error:
            continue
    return False


def click_first_enabled(page: "Page", selector: str) -> bool:
    targets = page.locator(selector)
    for index in range(targets.count()):
        target = targets.nth(index)
        try:
            if target.is_visible(timeout=500) and target.is_enabled(timeout=500):
                target.click(timeout=2_000)
                return True
        except Error:
            continue
    return False


def is_available(page: "Page", config: WatchConfig) -> bool:
    text = visible_text(page)
    available_seen = bool(compile_text_pattern(config.available_text).search(text))
    unavailable_seen = bool(compile_text_pattern(config.unavailable_text).search(text))
    clickable_seen = (
        has_enabled_click_target(page, config.click_selector)
        if config.click_selector
        else False
    )
    return clickable_seen or (available_seen and not unavailable_seen)


def watch(config: WatchConfig) -> int:
    if sync_playwright is None:
        print(
            "playwright가 설치되어 있지 않습니다.\n"
            "설치: python3 -m pip install -r requirements.txt\n"
            "브라우저 설치: python3 -m playwright install chromium",
            file=sys.stderr,
        )
        return 69

    deadline = (
        time.monotonic() + config.timeout_minutes * 60
        if config.timeout_minutes is not None
        else None
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=config.headless,
            viewport={"width": 1440, "height": 1000},
            locale="ko-KR",
        )
        page = browser.new_page()
        page.goto(config.url, wait_until="domcontentloaded", timeout=60_000)

        if config.once:
            print("1회 확인 모드로 실행합니다.")
        else:
            print("브라우저가 열렸습니다. 로그인이 필요하면 직접 로그인하세요.")
        print(f"감시 시작: {config.url}")

        attempt = 1
        last_alert_at: float | None = None
        while True:
            if deadline and time.monotonic() > deadline:
                print("타임아웃에 도달했습니다.")
                browser.close()
                return 2

            try:
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(1_000)

                if is_available(page, config):
                    print("예약 가능 신호를 찾았습니다.")
                    now = time.monotonic()
                    cooldown_seconds = config.alert_cooldown_minutes * 60
                    should_alert = (
                        last_alert_at is None
                        or now - last_alert_at >= cooldown_seconds
                    )
                    if should_alert:
                        notify("네이버 예약", "예약 가능 신호를 찾았습니다.", config)
                        last_alert_at = now
                    else:
                        print("알림 쿨다운 중이라 이번 알림은 건너뜁니다.")

                    if config.click_selector:
                        clicked = click_first_enabled(page, config.click_selector)
                        print("예약 버튼을 클릭했습니다." if clicked else "클릭 가능한 대상은 찾지 못했습니다.")

                    if config.continue_after_alert:
                        attempt += 1
                        time.sleep(config.interval_seconds)
                        continue

                    if not config.headless and not config.once:
                        page.bring_to_front()
                        print("브라우저에서 남은 예약 절차를 직접 확인하세요.")
                        input("종료하려면 Enter를 누르세요...")
                    browser.close()
                    return 0

                print(f"[{attempt}] 아직 예약 가능 신호가 없습니다.")
                if config.once:
                    browser.close()
                    return 0
            except TimeoutError as exc:
                print(f"[{attempt}] 페이지 로딩 타임아웃: {exc}")
                if config.once:
                    browser.close()
                    return 2
            except Error as exc:
                print(f"[{attempt}] 브라우저 오류: {exc}")
                if config.once:
                    browser.close()
                    return 2

            attempt += 1
            time.sleep(config.interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="네이버 예약 페이지 감시 도구")
    parser.add_argument(
        "url",
        nargs="?",
        default=os.getenv("RESERVATION_URL"),
        help="감시할 네이버 예약 URL. 기본값은 RESERVATION_URL 환경변수.",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(Path.home() / ".naver-reservation-watch"),
        help="로그인 세션을 저장할 브라우저 프로필 폴더",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="새로고침 간격(초)")
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=None,
        help="지정한 분 뒤 종료. 기본값은 계속 실행.",
    )
    parser.add_argument("--available-text", default=None, help="예약 가능 텍스트. 쉼표 구분.")
    parser.add_argument("--unavailable-text", default=None, help="예약 불가 텍스트. 쉼표 구분.")
    parser.add_argument(
        "--click-selector",
        default=None,
        help='예약 가능 시 클릭할 CSS selector. 예: button:has-text("예약하기")',
    )
    parser.add_argument("--headless", action="store_true", help="브라우저를 화면에 띄우지 않음")
    parser.add_argument("--no-sound", action="store_true", help="알림음 끄기")
    parser.add_argument("--once", action="store_true", help="한 번만 확인하고 종료")
    parser.add_argument(
        "--continue-after-alert",
        action="store_true",
        help="예약 가능 알림을 보낸 뒤 종료하지 않고 계속 감시",
    )
    parser.add_argument(
        "--alert-cooldown-minutes",
        type=float,
        default=float(os.getenv("ALERT_COOLDOWN_MINUTES", "30")),
        help="중복 텔레그램 알림을 막기 위한 대기 시간(분). 기본값은 30.",
    )
    parser.add_argument(
        "--telegram-bot-token",
        default=os.getenv("TELEGRAM_BOT_TOKEN"),
        help="텔레그램 봇 토큰. 기본값은 TELEGRAM_BOT_TOKEN 환경변수.",
    )
    parser.add_argument(
        "--telegram-chat-id",
        default=os.getenv("TELEGRAM_CHAT_ID"),
        help="텔레그램 채팅 ID. 기본값은 TELEGRAM_CHAT_ID 환경변수.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if not args.url:
        print("예약 URL을 인자로 넣거나 RESERVATION_URL 환경변수로 설정하세요.", file=sys.stderr)
        return 64
    if args.interval < 3:
        print("서버 부담을 줄이기 위해 --interval은 3초 이상으로 설정하세요.", file=sys.stderr)
        return 64
    if args.alert_cooldown_minutes < 0:
        print("--alert-cooldown-minutes는 0 이상으로 설정하세요.", file=sys.stderr)
        return 64

    config = WatchConfig(
        url=args.url,
        profile_dir=Path(args.profile_dir).expanduser(),
        interval_seconds=args.interval,
        timeout_minutes=args.timeout_minutes,
        available_text=parse_csv(args.available_text, DEFAULT_AVAILABLE_TEXT),
        unavailable_text=parse_csv(args.unavailable_text, DEFAULT_UNAVAILABLE_TEXT),
        click_selector=args.click_selector,
        headless=args.headless,
        sound=not args.no_sound,
        once=args.once,
        continue_after_alert=args.continue_after_alert,
        alert_cooldown_minutes=args.alert_cooldown_minutes,
        telegram_bot_token=args.telegram_bot_token,
        telegram_chat_id=args.telegram_chat_id,
    )
    os.makedirs(config.profile_dir, exist_ok=True)
    return watch(config)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
