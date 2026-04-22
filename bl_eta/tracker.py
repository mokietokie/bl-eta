"""track-trace.com Playwright async tracker.

Phase 1 최우선 검증: Bot 차단 유무 + 선사별 HTML 구조 실측.
CLI: `uv run python -m bl_eta.tracker <BL_NO> [--headed] [--dump DIR]`
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from bl_eta import parser

TRACK_TRACE_URL = "https://www.track-trace.com/bol"
# plan.md 7.1: 렌더링 대기 최대 30초 기준.
RENDER_TIMEOUT_MS = 30_000
IFRAME_RENDER_TIMEOUT_MS = 30_000
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

# track-trace.com 폼 구조 (Phase 1 실측):
#   action="/bol" method=POST target="_blank"
#   <input name="number"> + <input type=submit name="commit"> ("Track with options")
# 제출 시 새 탭에서 aggregation 결과 페이지가 열리고, 실제 tracking 데이터는
# <iframe class="track_res_frame" src="https://<carrier-site>/..."> 안에 렌더링됨.
# 선사 탭: <wc-multi-track-tab data-text="Maersk Line" data-tab-active="true">.
BL_INPUT_SELECTOR = 'form#bolform input[name="number"]'
SUBMIT_BUTTON_SELECTOR = 'form#bolform input[type="submit"][name="commit"]'
RESULT_FRAME_SELECTOR = 'iframe.track_res_frame'
ACTIVE_CARRIER_SELECTOR = 'wc-multi-track-tab[data-tab-active="true"]'

async def _submit_and_capture(context: BrowserContext, page: Page, bl_no: str) -> Page:
    """폼 제출 후 target="_blank"로 열리는 결과 페이지 반환."""
    await page.goto(TRACK_TRACE_URL, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
    await page.locator(BL_INPUT_SELECTOR).fill(bl_no)
    async with context.expect_page(timeout=RENDER_TIMEOUT_MS) as new_page_info:
        await page.locator(SUBMIT_BUTTON_SELECTOR).click()
    result_page = await new_page_info.value
    await result_page.wait_for_load_state("domcontentloaded", timeout=RENDER_TIMEOUT_MS)
    return result_page


async def _read_carrier(page: Page) -> str | None:
    try:
        el = page.locator(ACTIVE_CARRIER_SELECTOR).first
        return (await el.get_attribute("data-text")) or None
    except Exception:
        return None


async def _dismiss_cookie_banner(frame: Any) -> None:
    """Maersk (코이(coi-consent-banner) 기반) 등 쿠키 배너를 'Essential only'로 닫기.

    실패해도 조용히 넘어감 — 배너가 없거나 버튼명이 다를 수 있음.
    """
    candidates = [
        'button:has-text("Essential only")',
        'button:has-text("Allow all")',
        'button:has-text("Accept all")',
        'button:has-text("Accept")',
    ]
    for sel in candidates:
        try:
            btn = frame.locator(sel).first
            await btn.wait_for(state="visible", timeout=2_000)
            await btn.click(timeout=2_000)
            return
        except Exception:
            continue


async def _wait_for_tracking_content(frame: Any) -> None:
    """tracking 데이터(arrival date 라벨) 또는 명시적 'No results' 문구 출현 대기."""
    try:
        await frame.wait_for_function(
            """() => {
                const t = (document.body && document.body.innerText) || '';
                const low = t.toLowerCase();
                return low.includes('estimated arrival')
                    || low.includes('no results found')
                    || low.includes('access denied');
            }""",
            timeout=IFRAME_RENDER_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        pass


async def _kmtc_resubmit(frame: Any, bl_no: str) -> None:
    """KMTC(e-kmtc) iframe은 BL을 한 번 더 입력·검색해야 결과가 뜬다.

    iframe SPA에 '조회 / B/L No. / <input> / 검색' 폼이 있음.
    BL을 채우고 '검색' 버튼 클릭 → 결과 테이블 렌더링 대기.
    """
    # SPA 로드 여유
    try:
        await frame.wait_for_load_state("domcontentloaded", timeout=IFRAME_RENDER_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass

    # BL 입력창 찾기 — 값이 이미 있으면 그대로, 없으면 채움. Enter 제출.
    target_input = None
    try:
        inputs = frame.locator('input[type="text"]:not([readonly])')
        count = await inputs.count()
        for i in range(count):
            el = inputs.nth(i)
            try:
                if not await el.is_visible():
                    continue
                current = (await el.input_value()) or ""
                # BL이 이미 들어있거나 비어있는 input만 후보
                if current == bl_no or not current:
                    target_input = el
                    break
            except Exception:
                continue
    except Exception:
        pass

    clicked = False
    if target_input is not None:
        try:
            current = (await target_input.input_value()) or ""
            if current != bl_no:
                await target_input.fill(bl_no)
            await target_input.press("Enter")
            clicked = True
        except Exception:
            pass

    # Enter가 안 먹었을 경우: Cargo Tracking 패널 내부 'Search' 버튼 명시적 클릭
    if not clicked:
        candidates = (
            '.cargo-tracking button:has-text("Search")',
            'section:has-text("Cargo Tracking") button:has-text("Search")',
            'button.btn-primary:has-text("Search")',
            'button.btn-primary:has-text("검색")',
        )
        for sel in candidates:
            try:
                btn = frame.locator(sel).first
                await btn.wait_for(state="visible", timeout=2_000)
                await btn.click(timeout=2_000)
                clicked = True
                break
            except Exception:
                continue

    if not clicked:
        return

    # 결과 테이블/행이 떠오를 때까지 대기 (BUSAN/VISAKHAPATNAM 등 도시명이나 '조회 결과' 문구)
    try:
        await frame.wait_for_function(
            """() => {
                const t = (document.body && document.body.innerText) || '';
                const up = t.toUpperCase();
                return up.includes('BUSAN') || up.includes('PUSAN') || up.includes('INCHEON')
                    || t.includes('조회 결과') || t.includes('검색 결과')
                    || up.includes('NO DATA') || up.includes('NO RESULT');
            }""",
            timeout=IFRAME_RENDER_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        pass


async def _handle_carrier_iframe(frame: Any, iframe_src: str, bl_no: str) -> None:
    """iframe host 별 후처리 (KMTC 재조회 등)."""
    host = iframe_src.lower()
    if "ekmtc.com" in host:
        await _kmtc_resubmit(frame, bl_no)


# iframe 대신 선사 자체 사이트를 새 탭으로 여는 fallback 선사 (X-Frame-Options 차단 등).
# 이 선사들은 track-trace outer 페이지에 "Click here to show <carrier> results without frame"
# 링크가 노출되며, 클릭 시 선사 tracking 페이지가 새 탭에 열린다.
CARRIERS_USE_FULLSCREEN_LINK: tuple[str, ...] = ("HMM", "COSCO")

_FULLSCREEN_LINK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"show\s+.+?results?\s+without\s+frame", re.IGNORECASE),
    re.compile(r"show\s+tracking\s+results?\s+without\s+frame", re.IGNORECASE),
)


async def _follow_fullscreen_link(
    context: BrowserContext, result_page: Page, bl_no: str
) -> tuple[str, str, str]:
    """outer 결과 페이지에서 'show X results without frame' 링크 클릭 → 새 탭 캡처.

    반환: (carrier_site_url, rendered_html, innerText)
    링크를 못찾으면 빈 문자열 튜플 반환.
    """
    link = None
    for pattern in _FULLSCREEN_LINK_PATTERNS:
        try:
            loc = result_page.get_by_text(pattern).first
            if await loc.count() > 0:
                link = loc
                break
        except Exception:
            continue

    if link is None:
        return "", "", ""

    carrier_page: Page | None = None
    try:
        async with context.expect_page(timeout=RENDER_TIMEOUT_MS) as info:
            await link.click()
        carrier_page = await info.value
    except Exception:
        # target=_self 등 같은 탭 이동일 경우
        try:
            await link.click()
            carrier_page = result_page
        except Exception:
            return "", "", ""

    try:
        await carrier_page.wait_for_load_state("domcontentloaded", timeout=RENDER_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass

    # COSCO: track-trace는 'COSU'만 strip해 number=S<10digits>를 보내는데
    # COSCO 사이트는 순수 10자리 숫자로만 조회 가능. URL을 덮어쓰고 재 navigate.
    if "elines.coscoshipping.com" in carrier_page.url:
        digits = "".join(ch for ch in bl_no if ch.isdigit())
        if digits:
            fixed = re.sub(r"(number=)S?\d+", lambda m: m.group(1) + digits, carrier_page.url)
            if fixed != carrier_page.url:
                try:
                    await carrier_page.goto(fixed, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass
        # 쿠키 배너 닫아야 내부 iframe이 완전 렌더됨
        await _dismiss_cookie_banner(carrier_page)

    try:
        await carrier_page.wait_for_load_state("networkidle", timeout=RENDER_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass

    # SPA 추가 렌더 여유
    try:
        await carrier_page.wait_for_timeout(3_000)
    except Exception:
        pass

    url = carrier_page.url
    try:
        html = await carrier_page.content()
    except Exception:
        html = ""
    # COSCO는 실제 tracking UI가 iframe#scctCargoTracking 내부에 렌더링됨.
    inner_frame = None
    try:
        scct_el = await carrier_page.wait_for_selector(
            "iframe#scctCargoTracking", timeout=3_000
        )
        inner_frame = await scct_el.content_frame()
    except Exception:
        inner_frame = None

    if inner_frame is not None:
        try:
            await inner_frame.wait_for_load_state("domcontentloaded", timeout=RENDER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass
        try:
            await inner_frame.wait_for_load_state("networkidle", timeout=RENDER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass
        try:
            await inner_frame.wait_for_timeout(2_000)
        except Exception:
            pass
        try:
            text = await inner_frame.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception:
            text = ""
    else:
        try:
            text = await carrier_page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception:
            text = ""
    return url, html, text


async def _read_iframe(page: Page, bl_no: str) -> tuple[str, str, str]:
    """선사 iframe (src, rendered HTML, innerText)."""
    iframe_el = await page.wait_for_selector(RESULT_FRAME_SELECTOR, timeout=RENDER_TIMEOUT_MS)
    src = await iframe_el.get_attribute("src") or ""
    frame = await iframe_el.content_frame()
    if frame is None:
        return src, "", ""
    try:
        await frame.wait_for_load_state("domcontentloaded", timeout=IFRAME_RENDER_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass
    await _dismiss_cookie_banner(frame)
    await _handle_carrier_iframe(frame, src, bl_no)
    await _wait_for_tracking_content(frame)
    try:
        body_html = await frame.content()
    except Exception:
        body_html = ""
    try:
        body_text = await frame.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        body_text = ""
    return src, body_html, body_text


_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


async def _new_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="Asia/Seoul",
    )
    await context.add_init_script(_INIT_SCRIPT)
    return context


async def _run_one(
    context: BrowserContext, bl_no: str, dump_path: Path | None
) -> dict[str, Any]:
    """1 BL: 제출 → iframe/fullscreen 수집 → parser.parse."""
    page = await context.new_page()
    outer_html = ""
    iframe_html = ""
    iframe_text = ""
    iframe_src = ""
    carrier: str | None = None
    status = "ok"
    failure_reason = ""
    result_page: Page | None = None
    try:
        result_page = await _submit_and_capture(context, page, bl_no)
        outer_html = await result_page.content()
        carrier = await _read_carrier(result_page)
        if carrier and any(name in carrier for name in CARRIERS_USE_FULLSCREEN_LINK):
            iframe_src, iframe_html, iframe_text = await _follow_fullscreen_link(
                context, result_page, bl_no
            )
        else:
            iframe_src, iframe_html, iframe_text = await _read_iframe(result_page, bl_no)
    except Exception as e:
        status = "failed"
        failure_reason = f"{type(e).__name__}: {e}"
        if result_page is not None and not outer_html:
            try:
                outer_html = await result_page.content()
            except Exception:
                pass

    if dump_path is not None:
        dump_path.mkdir(parents=True, exist_ok=True)
        (dump_path / f"{bl_no}.outer.html").write_text(outer_html or "", encoding="utf-8")
        (dump_path / f"{bl_no}.iframe.html").write_text(iframe_html or "", encoding="utf-8")
        (dump_path / f"{bl_no}.iframe.txt").write_text(iframe_text or "", encoding="utf-8")
        meta = f"carrier={carrier}\niframe_src={iframe_src}\nstatus={status}\nerror={failure_reason}\n"
        (dump_path / f"{bl_no}.meta.txt").write_text(meta, encoding="utf-8")
        target = result_page or page
        try:
            await target.screenshot(path=str(dump_path / f"{bl_no}.png"), full_page=True)
        except Exception:
            pass

    if status == "failed":
        return {
            "bl_no": bl_no, "carrier": carrier, "port": None, "eta": None,
            "status": "failed", "raw_text": (iframe_text or iframe_html or outer_html or "")[:2000],
        }
    return parser.parse(bl_no, iframe_text, carrier=carrier)


async def track(
    bl_no: str,
    *,
    headless: bool = True,
    dump_path: Path | None = None,
) -> dict[str, Any]:
    """단일 BL 조회 → parser.parse 결과 dict."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await _new_context(browser)
        try:
            return await _run_one(context, bl_no, dump_path)
        finally:
            await browser.close()


ProgressCb = Any  # Callable[[int, int, str, dict], None] — 동기 콜백


async def track_many(
    bl_list: list[str],
    *,
    headless: bool = True,
    concurrency: int = 5,
    dump_path: Path | None = None,
    on_progress: ProgressCb = None,
) -> list[dict[str, Any]]:
    """다수 BL 병렬 조회. 결과는 입력 순서와 동일한 인덱스.

    동시성: asyncio.Semaphore(concurrency). BL별 별도 context로 격리
    (HMM fullscreen 새 탭 capture가 context-scoped expect_page 의존).
    """
    if not bl_list:
        return []
    concurrency = max(1, min(concurrency, len(bl_list)))
    results: list[dict[str, Any] | None] = [None] * len(bl_list)
    completed = 0
    lock = asyncio.Lock()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        sem = asyncio.Semaphore(concurrency)

        async def worker(idx: int, bl: str) -> None:
            nonlocal completed
            async with sem:
                context = await _new_context(browser)
                try:
                    try:
                        rec = await _run_one(context, bl, dump_path)
                    except Exception as e:
                        rec = {
                            "bl_no": bl, "carrier": None, "port": None, "eta": None,
                            "status": "failed", "raw_text": f"{type(e).__name__}: {e}",
                        }
                finally:
                    try:
                        await context.close()
                    except Exception:
                        pass
                results[idx] = rec
                async with lock:
                    completed += 1
                    done = completed
                if on_progress is not None:
                    try:
                        on_progress(done, len(bl_list), bl, rec)
                    except Exception:
                        pass

        try:
            await asyncio.gather(*(worker(i, bl) for i, bl in enumerate(bl_list)))
        finally:
            await browser.close()

    return [r if r is not None else {
        "bl_no": bl_list[i], "carrier": None, "port": None, "eta": None,
        "status": "failed", "raw_text": "no result",
    } for i, r in enumerate(results)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bl_eta.tracker", description="track-trace.com BL ETA lookup")
    p.add_argument("bl_no", help="BL number (e.g. MAEU1234567)")
    p.add_argument("--headed", action="store_true", help="show browser window")
    p.add_argument("--dump", type=Path, default=None, help="dump HTML/screenshot to this directory")
    args = p.parse_args(argv)
    result = asyncio.run(track(args.bl_no, headless=not args.headed, dump_path=args.dump))
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
