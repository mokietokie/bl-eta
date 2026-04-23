"""VesselFinder 선명/IMO → 현재 위치(가장 가까운 연안 국가) 추출.

두 경로:
  1) IMO 직접 조회 (권장): `/?imo=<IMO>` 지도 페이지 직행 → meta description 파싱.
  2) 선명 검색 폴백: `vessels?name=...` → Container Ship 첫 결과 상세 → Track on Map →
     지도 페이지. 이름 검색이 성공하면 detail_url에서 IMO를 추출해 결과 dict에 채운다.

좌표 → reverse_geocoder(오프라인) → ISO2 → `_CC_KO` 한국어 국가명.

CLI:
  `uv run python -m bl_eta.vesselfinder "MONACO MAERSK"`  (이름 검색)
  `uv run python -m bl_eta.vesselfinder --imo 9778832`     (IMO 직접)
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

import reverse_geocoder as _rg

_RG_LOCK = threading.Lock()


def _warmup_rg() -> None:
    # reverse_geocoder는 모듈 싱글톤을 lazy init하며 스레드-세이프하지 않다.
    # 병렬 워커가 초기화 중인 내부 구조를 동시에 순회하면
    # "dictionary changed size during iteration"이 발생하므로 import 시점에 강제 초기화.
    try:
        _rg.search([(0.0, 0.0)], mode=1)
    except Exception:
        pass


_warmup_rg()
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from bl_eta.tracker import RENDER_TIMEOUT_MS, _new_context

SEARCH_URL = "https://www.vesselfinder.com/vessels?name={name}"
IMO_MAP_URL = "https://www.vesselfinder.com/?imo={imo}"
DETAIL_URL_RE = re.compile(r"/vessels/details/(\d+)", re.IGNORECASE)
TRACK_ON_MAP_RE = re.compile(r"track\s+on\s+map", re.IGNORECASE)
IMO_RE = re.compile(r"^\d{7}$")
DUMP_DIR = Path.home() / ".bl-eta"

# 지도 페이지 HTML meta description 예:
#   "MONACO MAERSK last position is 8 N, 16 W heading to Singapore ..."
_META_POS_RE = re.compile(
    r"last\s+position\s+is\s+"
    r"(?P<lat>\d+(?:\.\d+)?)\s*(?P<ns>[NS])\s*,?\s*"
    r"(?P<lon>\d+(?:\.\d+)?)\s*(?P<ew>[EW])",
    re.IGNORECASE,
)
_META_TAG_RE = re.compile(
    r'<meta\s+name="description"\s+content="([^"]*)"', re.IGNORECASE
)

# ISO-3166 alpha-2 → 한국어 국가명 (컨테이너선 항로 빈출 국가 중심).
# 매핑 없는 코드는 원본 ISO2 코드로 폴백.
_CC_KO = {
    "KR": "대한민국", "KP": "북한", "JP": "일본", "CN": "중국", "TW": "대만",
    "HK": "홍콩", "MO": "마카오", "SG": "싱가포르", "MY": "말레이시아",
    "TH": "태국", "VN": "베트남", "ID": "인도네시아", "PH": "필리핀",
    "MM": "미얀마", "KH": "캄보디아", "LA": "라오스", "BN": "브루나이",
    "IN": "인도", "PK": "파키스탄", "BD": "방글라데시", "LK": "스리랑카",
    "NP": "네팔", "MV": "몰디브",
    "AE": "아랍에미리트", "SA": "사우디아라비아", "OM": "오만", "QA": "카타르",
    "KW": "쿠웨이트", "BH": "바레인", "IR": "이란", "IQ": "이라크",
    "IL": "이스라엘", "JO": "요르단", "LB": "레바논", "SY": "시리아",
    "TR": "튀르키예", "YE": "예멘",
    "EG": "이집트", "LY": "리비아", "TN": "튀니지", "DZ": "알제리", "MA": "모로코",
    "SD": "수단", "SS": "남수단", "ET": "에티오피아", "DJ": "지부티",
    "SO": "소말리아", "KE": "케냐", "TZ": "탄자니아", "MZ": "모잠비크",
    "ZA": "남아프리카공화국", "NA": "나미비아", "AO": "앙골라",
    "CD": "콩고민주공화국", "CG": "콩고", "GA": "가봉", "CM": "카메룬",
    "NG": "나이지리아", "BJ": "베냉", "TG": "토고", "GH": "가나",
    "CI": "코트디부아르", "LR": "라이베리아", "SL": "시에라리온",
    "GN": "기니", "GW": "기니비사우", "SN": "세네갈", "GM": "감비아",
    "MR": "모리타니", "CV": "카보베르데", "MG": "마다가스카르",
    "MU": "모리셔스", "SC": "세이셸",
    "GB": "영국", "IE": "아일랜드", "FR": "프랑스", "DE": "독일",
    "NL": "네덜란드", "BE": "벨기에", "LU": "룩셈부르크", "CH": "스위스",
    "AT": "오스트리아", "IT": "이탈리아", "ES": "스페인", "PT": "포르투갈",
    "GR": "그리스", "CY": "키프로스", "MT": "몰타",
    "DK": "덴마크", "NO": "노르웨이", "SE": "스웨덴", "FI": "핀란드", "IS": "아이슬란드",
    "PL": "폴란드", "CZ": "체코", "SK": "슬로바키아", "HU": "헝가리",
    "RO": "루마니아", "BG": "불가리아", "HR": "크로아티아", "SI": "슬로베니아",
    "RS": "세르비아", "AL": "알바니아",
    "RU": "러시아", "UA": "우크라이나", "BY": "벨라루스",
    "EE": "에스토니아", "LV": "라트비아", "LT": "리투아니아",
    "US": "미국", "CA": "캐나다", "MX": "멕시코", "CU": "쿠바",
    "JM": "자메이카", "DO": "도미니카공화국", "HT": "아이티",
    "BS": "바하마", "PR": "푸에르토리코",
    "GT": "과테말라", "HN": "온두라스", "SV": "엘살바도르",
    "NI": "니카라과", "CR": "코스타리카", "PA": "파나마",
    "CO": "콜롬비아", "VE": "베네수엘라", "EC": "에콰도르",
    "PE": "페루", "BR": "브라질", "BO": "볼리비아",
    "CL": "칠레", "AR": "아르헨티나", "UY": "우루과이", "PY": "파라과이",
    "GY": "가이아나", "SR": "수리남",
    "AU": "호주", "NZ": "뉴질랜드", "PG": "파푸아뉴기니", "FJ": "피지",
    "SB": "솔로몬제도", "VU": "바누아투", "NC": "뉴칼레도니아",
}


def _parse_latlon_from_html(html: str) -> tuple[float, float] | None:
    """지도 페이지 HTML의 meta description에서 위도/경도 추출."""
    tag = _META_TAG_RE.search(html)
    content = tag.group(1) if tag else html
    m = _META_POS_RE.search(content)
    if not m:
        return None
    lat = float(m.group("lat"))
    lon = float(m.group("lon"))
    if m.group("ns").upper() == "S":
        lat = -lat
    if m.group("ew").upper() == "W":
        lon = -lon
    return lat, lon


def _nearest_country_ko(lat: float, lon: float) -> tuple[str, str, str]:
    """좌표 → (한국어 국가명, ISO2, 가장 가까운 도시명). 오프라인 reverse_geocoder."""
    with _RG_LOCK:
        hits = _rg.search([(lat, lon)], mode=1)
    if not hits:
        return "알 수 없음", "", ""
    rec = hits[0]
    cc = (rec.get("cc") or "").upper()
    city = rec.get("name") or ""
    country_ko = _CC_KO.get(cc, cc or "알 수 없음")
    return country_ko, cc, city


def _format_label(country_ko: str, city: str) -> str:
    if city:
        return f"{country_ko} 앞바다 ({city} 인근)"
    return f"{country_ko} 앞바다"


async def _click_first_container_ship(page: Page) -> None:
    row = (
        page.locator('tr:has(a[href^="/vessels/details/"])')
        .filter(has_text=re.compile(r"container ship", re.I))
        .first
    )
    try:
        await row.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeoutError:
        DUMP_DIR.mkdir(parents=True, exist_ok=True)
        (DUMP_DIR / "vf-search-dump.html").write_text(
            await page.content(), encoding="utf-8"
        )
        raise RuntimeError("Container Ship 결과 행을 찾지 못했습니다.")

    link = row.locator('a[href^="/vessels/details/"]').first
    href = await link.get_attribute("href")
    if href:
        target = href if href.startswith("http") else f"https://www.vesselfinder.com{href}"
        await page.goto(target, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
    else:
        await link.click()


async def _click_track_on_map(page: Page) -> None:
    candidates = (
        lambda: page.get_by_role("link", name=TRACK_ON_MAP_RE).first,
        lambda: page.get_by_role("button", name=TRACK_ON_MAP_RE).first,
        lambda: page.locator("a, button").filter(has_text=TRACK_ON_MAP_RE).first,
    )
    last_err: Exception | None = None
    for build in candidates:
        try:
            loc = build()
            await loc.wait_for(state="visible", timeout=10_000)
            await loc.click(timeout=6_000)
            return
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"'Track on Map' 버튼을 찾지 못했습니다 ({last_err})")


def _empty_result(vessel: str, imo: str | None, status: str, **extra) -> dict[str, Any]:
    rec = {
        "vessel": vessel, "imo": imo, "status": status,
        "lat": None, "lon": None,
        "country_ko": None, "cc": None, "nearest_city": None,
        "location_label": None, "detail_url": None, "map_url": None,
    }
    rec.update(extra)
    return rec


async def _lookup_by_imo(
    context: BrowserContext, imo: str, vessel_hint: str | None = None
) -> dict[str, Any]:
    """IMO 직접 조회 — `/?imo=<IMO>` 지도 페이지 1회 진입으로 끝낸다.

    검색→상세→Track on Map 3단계 생략. 동명이선 RISK도 IMO로 해소.
    """
    page = await context.new_page()
    map_url = IMO_MAP_URL.format(imo=imo)
    vessel = vessel_hint or ""
    try:
        await page.goto(map_url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
        try:
            await page.wait_for_timeout(2_000)
        except Exception:
            pass
        html = await page.content()
        latlon = _parse_latlon_from_html(html)
        if latlon is None:
            DUMP_DIR.mkdir(parents=True, exist_ok=True)
            (DUMP_DIR / f"vf-map-dump-{imo}.html").write_text(html, encoding="utf-8")
            return _empty_result(
                vessel, imo, "failed",
                map_url=map_url,
                error="meta description 좌표 파싱 실패 (IMO 직접)",
            )
        lat, lon = latlon
        country_ko, cc, city = _nearest_country_ko(lat, lon)
        return _empty_result(
            vessel, imo, "ok",
            lat=lat, lon=lon,
            country_ko=country_ko, cc=cc, nearest_city=city,
            location_label=_format_label(country_ko, city),
            map_url=map_url,
        )
    except Exception as e:
        return _empty_result(
            vessel, imo, "failed",
            map_url=map_url,
            error=f"{type(e).__name__}: {e}",
        )
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _lookup_by_name(
    context: BrowserContext, vessel_name: str
) -> dict[str, Any]:
    """선명 검색 폴백. 성공 시 detail_url의 IMO를 결과 dict에 채움 (백필 용도)."""
    page = await context.new_page()
    try:
        await page.goto(
            SEARCH_URL.format(name=quote_plus(vessel_name)),
            wait_until="domcontentloaded",
            timeout=RENDER_TIMEOUT_MS,
        )
        try:
            await _click_first_container_ship(page)
        except RuntimeError:
            return _empty_result(vessel_name, None, "not_found")
        try:
            await page.wait_for_url(DETAIL_URL_RE, timeout=25_000)
        except PlaywrightTimeoutError:
            pass
        detail_url = page.url
        m_imo = DETAIL_URL_RE.search(detail_url)
        if not m_imo:
            raise RuntimeError(f"상세페이지 전환 실패: {detail_url}")
        extracted_imo = m_imo.group(1)

        try:
            await page.wait_for_timeout(1_500)
        except Exception:
            pass

        await _click_track_on_map(page)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=RENDER_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            pass
        try:
            await page.wait_for_timeout(2_000)
        except Exception:
            pass
        map_url = page.url
        html = await page.content()

        latlon = _parse_latlon_from_html(html)
        if latlon is None:
            return _empty_result(
                vessel_name, extracted_imo, "failed",
                detail_url=detail_url, map_url=map_url,
                error="meta description 좌표 파싱 실패 (이름 검색)",
            )
        lat, lon = latlon
        country_ko, cc, city = _nearest_country_ko(lat, lon)
        return _empty_result(
            vessel_name, extracted_imo, "ok",
            lat=lat, lon=lon,
            country_ko=country_ko, cc=cc, nearest_city=city,
            location_label=_format_label(country_ko, city),
            detail_url=detail_url, map_url=map_url,
        )
    except Exception as e:
        return _empty_result(
            vessel_name, None, "failed",
            error=f"{type(e).__name__}: {e}",
        )
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def _lookup_one(
    context: BrowserContext, vessel_name: str, imo: str | None = None
) -> dict[str, Any]:
    """단일 항목 → 위치 정보 dict. IMO 7자리가 있으면 직접 조회, 아니면 이름 검색.

    status: 'ok' | 'not_found' | 'failed'
    """
    imo_clean = (imo or "").strip()
    if imo_clean and IMO_RE.fullmatch(imo_clean):
        return await _lookup_by_imo(context, imo_clean, vessel_name)
    return await _lookup_by_name(context, vessel_name)


async def _lookup_with_retry(
    context: BrowserContext,
    vessel_name: str,
    imo: str | None = None,
    *,
    attempts: int = 2,
    backoff_s: float = 2.0,
) -> dict[str, Any]:
    """failed면 1회 재시도. not_found는 결과가 안 바뀌므로 재시도하지 않는다."""
    last: dict[str, Any] | None = None
    for i in range(attempts):
        rec = await _lookup_one(context, vessel_name, imo)
        st = rec.get("status")
        if st == "ok":
            if i > 0:
                rec["retried"] = True
            return rec
        if st == "not_found":
            return rec
        last = rec
        if i < attempts - 1:
            await asyncio.sleep(backoff_s)
    return last or _empty_result(vessel_name, imo, "failed", error="알 수 없는 실패")


ProgressCb = Callable[[int, int, str, dict[str, Any]], None] | None


def _normalize_items(items: list[dict[str, Any] | str]) -> list[dict[str, Any]]:
    """str 또는 dict({"vessel","imo"}) 입력을 dict 리스트로 정규화."""
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, str):
            out.append({"vessel": it, "imo": None})
        else:
            out.append({"vessel": it.get("vessel") or "", "imo": it.get("imo")})
    return out


async def track_many_locations(
    items: list[dict[str, Any] | str],
    *,
    headless: bool = True,
    concurrency: int = 5,
    on_progress: ProgressCb = None,
) -> list[dict[str, Any]]:
    """다수 항목 병렬 위치 조회. 결과는 입력 순서 보존.

    items 원소: `str` (선명) 또는 `{"vessel": str, "imo": str | None}` dict.
    IMO가 7자리 숫자면 검색을 건너뛰고 지도 페이지로 직행한다.
    각 항목에 1회 자동 재시도 (failed인 경우만, not_found는 즉시 반환).
    """
    norm = _normalize_items(items)
    if not norm:
        return []
    concurrency = max(1, min(concurrency, len(norm)))
    results: list[dict[str, Any] | None] = [None] * len(norm)
    completed = 0
    lock = asyncio.Lock()

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        sem = asyncio.Semaphore(concurrency)

        async def worker(idx: int, item: dict[str, Any]) -> None:
            nonlocal completed
            vessel = item["vessel"]
            imo = item.get("imo")
            async with sem:
                ctx = await _new_context(browser)
                try:
                    rec = await _lookup_with_retry(ctx, vessel, imo)
                finally:
                    try:
                        await ctx.close()
                    except Exception:
                        pass
            results[idx] = rec
            async with lock:
                completed += 1
                done = completed
            if on_progress is not None:
                try:
                    on_progress(done, len(norm), vessel, rec)
                except Exception:
                    pass

        try:
            await asyncio.gather(*(worker(i, it) for i, it in enumerate(norm)))
        finally:
            await browser.close()

    return [
        r if r is not None else _empty_result(
            norm[i]["vessel"], norm[i].get("imo"), "failed",
            error="결과 누락",
        )
        for i, r in enumerate(results)
    ]


async def open_vessel_location(
    vessel_name: str, *, imo: str | None = None, headed: bool = True
) -> dict[str, Any]:
    """단일 항목 CLI 헬퍼. IMO가 있으면 직접 조회 사용."""
    item: dict[str, Any] = {"vessel": vessel_name, "imo": imo}
    results = await track_many_locations(
        [item], headless=not headed, concurrency=1
    )
    return results[0]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    imo: str | None = None
    name: str | None = None
    i = 0
    while i < len(args):
        if args[i] == "--imo" and i + 1 < len(args):
            imo = args[i + 1]
            i += 2
        else:
            name = args[i]
            i += 1
    if not imo and not name:
        name = "MONACO MAERSK"
    result = asyncio.run(open_vessel_location(name or "", imo=imo, headed=True))
    for key in (
        "vessel", "imo", "status", "detail_url", "map_url", "lat", "lon",
        "country_ko", "cc", "nearest_city", "location_label",
    ):
        if key in result:
            print(f"{key:>14}: {result.get(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
