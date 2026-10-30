"""오피넷에서 데이터를 모아 신호를 계산하고, 미니앱이 읽을 공개 파일(docs/data)을 만든다.

실행 모드
  full   : 매일 00:40 — 일평균 확정 후 전체 수집 (약 200회 호출)
  light  : 하루 4번 — 현재 전국·시도 평균만 갱신 (2회)
  weekly : 금요일 10:25 — 주간 평균 + light (3회)
  auto   : 수동 실행용 — 공개 파일이 없으면 full, 있으면 light

하루 한도 300회 중 280회까지만 쓰도록 state/state.json 에 날짜별 호출 수를 기록한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from opinet import (BRAND_NAMES, DIESEL, GASOLINE, LPG, PREMIUM, PRODUCT_NAMES,  # noqa: E402
                    BudgetExceeded, Opinet, OpinetError, to_float)
import signal_rules  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_PATH = os.path.join(ROOT, "state", "state.json")
HISTORY_PATH = os.path.join(ROOT, "state", "history.json")
EVENTS_PATH = os.path.join(ROOT, "config", "events.json")
OUT_DIR = os.path.join(ROOT, "docs", "data")

KST = timezone(timedelta(hours=9))
DAILY_LIMIT = 300
SAFETY_MARGIN = 20
MODE_BUDGET = {"full": 240, "light": 4, "weekly": 6}
MIN_NEED = {"full": 40, "light": 2, "weekly": 3}   # 이보다 적게 남으면 실행하지 않음
TRACKED = [GASOLINE, DIESEL, PREMIUM, LPG]
SIGNAL_PRODUCTS = [GASOLINE, DIESEL]
CAPITAL_AREA = ("서울", "경기", "인천")   # 시군구 단위 최저가까지 모으는 지역
HISTORY_DAYS = 60


# ---------- 파일 입출력 ----------
def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save(path, data, pretty=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        else:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def now_kst() -> datetime:
    override = os.environ.get("NOW_KST")  # 테스트용 시각 고정
    if override:
        return datetime.fromisoformat(override).replace(tzinfo=KST)
    return datetime.now(KST)


# ---------- 수집 단계 ----------
def collect_current(api: Opinet, out: dict):
    """현재 전국 평균 + 시도별 평균."""
    nat = {}
    for row in api.get("avgAllPrice"):
        code = row.get("PRODCD")
        if code in TRACKED:
            nat[code] = {"price": to_float(row.get("PRICE")), "diff": to_float(row.get("DIFF")),
                         "date": row.get("TRADE_DT")}
    if nat:
        out["national"] = nat

    sido: dict[str, dict] = {}
    for row in api.get("avgSidoPrice"):
        code = str(row.get("SIDOCD", "")).zfill(2)
        if code == "00" or not row.get("SIDONM"):
            continue
        item = sido.setdefault(code, {"code": code, "name": row.get("SIDONM")})
        prod = row.get("PRODCD")
        if prod in TRACKED:
            item[prod] = {"price": to_float(row.get("PRICE")), "diff": to_float(row.get("DIFF"))}
    if sido:
        out["sido"] = sorted(sido.values(), key=lambda x: x["code"])


def collect_daily(api: Opinet, history: dict, today: date):
    """최근 7일 확정 일평균. 기록이 짧으면 특정 7일 API로 4주치를 채운다."""
    daily = history.setdefault("daily", {})
    for row in api.get("avgRecentPrice"):
        prod, d, p = row.get("PRODCD"), row.get("DATE"), to_float(row.get("PRICE"))
        if prod in TRACKED and d and p:
            daily.setdefault(prod, {})[d] = p

    if len(daily.get(GASOLINE, {})) < 20:
        for weeks_back in (1, 2, 3):
            target = (today - timedelta(days=7 * weeks_back + 1)).strftime("%Y%m%d")
            for row in api.get("dateAvgRecentPrice", date=target):
                prod, d, p = row.get("PRODCD"), row.get("DATE"), to_float(row.get("PRICE"))
                if prod in TRACKED and d and p:
                    daily.setdefault(prod, {})[d] = p

    # 오래된 기록 정리
    cutoff = (today - timedelta(days=HISTORY_DAYS)).strftime("%Y%m%d")
    for prod in list(daily):
        daily[prod] = {d: p for d, p in daily[prod].items() if d >= cutoff}


def collect_weekly(api: Opinet, history: dict):
    weekly = history.setdefault("weekly_official", {})
    for row in api.get("avgLastWeek"):
        prod = row.get("PRODCD")
        if prod in TRACKED and str(row.get("AREA_CD", "00")).zfill(2) == "00":
            weekly.setdefault(prod, {})[str(row.get("WEEK")).strip()] = {
                "start": row.get("STA_DT"), "end": row.get("END_DT"), "price": to_float(row.get("PRICE"))}


def station(row: dict) -> dict:
    return {
        "id": row.get("UNI_ID"),
        "name": row.get("OS_NM"),
        "brand": BRAND_NAMES.get(row.get("POLL_DIV_CD") or row.get("POLL_DIV_CO"), row.get("POLL_DIV_CD") or ""),
        "price": to_float(row.get("PRICE")),
        "address": row.get("NEW_ADR") or row.get("VAN_ADR"),
    }


def collect_regions(api: Opinet, sido_list: list[dict], updated_at: str):
    """시도별: 시군구 평균, 시도 최저가 TOP10, 수도권은 시군구별 최저가 TOP5."""
    index = []
    # 1단계: 모든 시도의 시군구 평균 + 시도 최저가 (중요한 것부터)
    regions = {}
    for s in sido_list:
        code = s["code"]
        sigun: dict[str, dict] = {}
        for row in api.get("avgSigunPrice", sido=code):
            sc = str(row.get("SIGUNCD", "")).zfill(4)
            item = sigun.setdefault(sc, {"code": sc, "name": row.get("SIGUNNM")})
            prod = row.get("PRODCD")
            if prod in (GASOLINE, DIESEL):
                item[PRODUCT_NAMES[prod]] = {"price": to_float(row.get("PRICE")), "diff": to_float(row.get("DIFF"))}
        regions[code] = {"code": code, "name": s["name"], "updated_at": updated_at,
                         "sigun": sorted(sigun.values(), key=lambda x: x["code"]),
                         "lowest": {}, "lowest_sigun": {}}
        index.append({"code": code, "name": s["name"],
                      "sigun": [{"code": x["code"], "name": x["name"]} for x in regions[code]["sigun"]]})

    for code, r in regions.items():
        for prod in (GASOLINE, DIESEL):
            rows = api.get("lowTop10", prodcd=prod, area=code, cnt=10)
            r["lowest"][PRODUCT_NAMES[prod]] = [station(x) for x in rows]

    # 2단계: 수도권 시군구별 최저가 (예산이 남는 만큼)
    for code, r in regions.items():
        if not r["name"].startswith(CAPITAL_AREA):
            continue
        for sg in r["sigun"]:
            for prod in (GASOLINE, DIESEL):
                try:
                    rows = api.get("lowTop10", prodcd=prod, area=sg["code"], cnt=5)
                except BudgetExceeded:
                    return regions, index
                r["lowest_sigun"].setdefault(sg["code"], {})[PRODUCT_NAMES[prod]] = [station(x) for x in rows]
    return regions, index


# ---------- 메인 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="auto", choices=["auto", "full", "light", "weekly"])
    args = ap.parse_args()

    now = now_kst()
    today = now.date()
    today_key = today.isoformat()
    updated_at = now.isoformat(timespec="minutes")

    state = load(STATE_PATH, {})
    history = load(HISTORY_PATH, {})
    events = load(EVENTS_PATH, {})
    latest_path = os.path.join(OUT_DIR, "latest.json")
    latest = load(latest_path, {})

    mode = args.mode
    if mode == "auto":
        mode = "full" if not latest or not os.path.exists(os.path.join(OUT_DIR, "regions.json")) else "light"

    calls = state.setdefault("calls", {})
    used = calls.get(today_key, 0)
    remaining = DAILY_LIMIT - SAFETY_MARGIN - used
    budget = min(MODE_BUDGET[mode], remaining)
    print(f"[{updated_at}] mode={mode} 오늘 사용 {used}회, 이번 실행 예산 {budget}회")
    if budget < MIN_NEED[mode]:
        print("오늘 호출 한도에 가까워 실행하지 않아요.")
        return 0

    api = Opinet(os.environ.get("OPINET_KEY"), budget, os.environ.get("FIXTURE_DIR"))
    current: dict = {}
    errors = []
    try:
        collect_current(api, current)
        if mode == "weekly":
            collect_weekly(api, history)
        if mode == "full":
            collect_daily(api, history, today)
            sido_list = current.get("sido") or latest.get("sido") or []
            regions, index = collect_regions(api, sido_list, updated_at)
            for code, r in regions.items():
                save(os.path.join(OUT_DIR, "region", f"{code}.json"), r, pretty=False)
            if index:
                save(os.path.join(OUT_DIR, "regions.json"), {"updated_at": updated_at, "sido": index}, pretty=False)
    except BudgetExceeded as e:
        errors.append(str(e))
    except OpinetError as e:
        errors.append(str(e))
        print("오류:", e)
    finally:
        calls[today_key] = used + api.calls
        # 오래된 호출 기록 정리
        for k in sorted(calls)[:-14]:
            del calls[k]

    # ---------- 신호 계산 ----------
    daily = history.get("daily", {})
    signals = {}
    trend = {}
    for prod in SIGNAL_PRODUCTS:
        series = sorted(daily.get(prod, {}).items())
        name = PRODUCT_NAMES[prod]
        signals[name] = signal_rules.product_signal(name, series, events, today)
        trend[name] = [{"date": d, "price": p} for d, p in series[-30:]]
    tax = signal_rules.tax_card(events, today)

    prev_signals = state.get("signals", {})
    pushes = signal_rules.push_suggestions(prev_signals, signals, tax)
    for name, sig in signals.items():
        before = prev_signals.get(name, {})
        sig["since"] = before.get("since") if before.get("level") == sig["level"] else today_key
    state["signals"] = {k: {"level": v["level"], "since": v["since"]} for k, v in signals.items()}

    national = current.get("national") or latest.get("national") or {}
    out = {
        "updated_at": updated_at,
        "source": "한국석유공사 오피넷",
        "national": {PRODUCT_NAMES[k]: v for k, v in national.items()} if national and GASOLINE in national
        else national,
        "signal": signals,
        "trend": trend,
        "tax_cut": tax,
        "outlook": events.get("outlook"),
        "sido": [
            {"code": s["code"], "name": s["name"],
             **{PRODUCT_NAMES[p]: s[p] for p in (GASOLINE, DIESEL) if p in s}}
            for s in (current.get("sido") or [])
        ] or latest.get("sido", []),
        "notice": (events.get("notice") or None),
    }
    save(latest_path, out, pretty=False)
    if current.get("sido"):
        # 다음 full 실행 때 시도 목록으로 재사용
        state["sido_list"] = [{"code": s["code"], "name": s["name"]} for s in current["sido"]]

    if pushes:
        save(os.path.join(OUT_DIR, "push.json"), {"created_at": updated_at, "suggestions": pushes})
        state.setdefault("push_log", []).append({"at": updated_at, "suggestions": pushes})
        state["push_log"] = state["push_log"][-30:]

    state["last_run"] = {"at": updated_at, "mode": mode, "calls": api.calls, "errors": errors}
    save(STATE_PATH, state)
    save(HISTORY_PATH, history)

    print(f"호출 {api.calls}회 사용 (오늘 누적 {calls[today_key]}회)")
    for name, sig in signals.items():
        print(f"  {name}: {sig['level']} — {sig['title']} | " + " / ".join(sig["reasons"]))
    if pushes:
        print("알림 제안:", *[p["message"] for p in pushes], sep="\n  ")
    if errors:
        print("경고:", *errors, sep="\n  ")
    # 오피넷 접속 자체가 실패했고 결과가 하나도 없으면 실패로 표시해 알 수 있게 한다
    return 1 if errors and not current else 0


if __name__ == "__main__":
    sys.exit(main())
