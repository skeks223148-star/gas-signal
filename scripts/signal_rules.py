"""기름값 신호(빨강·초록·노랑) 계산 규칙.

원칙
- '내일 오른다'고 단정하지 않는다. 확정 일평균 추세 + 주간 평균 + 석유공사 전망(수동 입력)
  + 유류세 일정을 점수로 합쳐 '전망' 수준으로만 말한다.
- 유류세 인하 종료가 확정되면 다른 신호와 상관없이 빨강.
- 유류세 종료 여부가 미정인데 마감이 14일 이내면 초록(기다려도 됨)을 내지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime

LEVEL_TEXT = {
    "red": "이번 주 안에 넣으세요",
    "green": "서두르지 않아도 돼요",
    "yellow": "큰 변화 없어요",
}

LEVEL_SUB = {
    "red": "기름값이 오를 전망이에요",
    "green": "기름값이 내리는 중이에요",
    "yellow": "평소대로 넣어도 괜찮아요",
}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date() if "-" in s else datetime.strptime(s, "%Y%m%d").date()


def streak(prices: list[float]) -> tuple[int, int]:
    """끝에서부터 연속 상승/하락 일수."""
    ups = downs = 0
    for i in range(len(prices) - 1, 0, -1):
        diff = prices[i] - prices[i - 1]
        if diff > 0.05 and downs == 0:
            ups += 1
        elif diff < -0.05 and ups == 0:
            downs += 1
        else:
            break
    return ups, downs


def weekly_means(daily: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """일평균을 일요일 시작 주 단위로 묶어 평균(5일 이상 있는 주만)."""
    buckets: dict[str, list[float]] = {}
    for ds, p in daily:
        d = _d(ds)
        # 일요일 시작 주: 일요일=6 → 0
        offset = (d.weekday() + 1) % 7
        start = date.fromordinal(d.toordinal() - offset).isoformat()
        buckets.setdefault(start, []).append(p)
    out = [(k, round(sum(v) / len(v), 2)) for k, v in sorted(buckets.items()) if len(v) >= 5]
    return out


def product_signal(product_name: str, daily: list[tuple[str, float]], events: dict, today: date) -> dict:
    """daily: [(YYYYMMDD, 가격)] 오래된 순."""
    score = 0
    reasons: list[str] = []
    prices = [p for _, p in daily]
    capped_by_tax = False

    # 1) 최근 3일 확정 일평균 추세 (국내 가격은 한번 방향이 잡히면 1~2주 이어지는 경향)
    if len(prices) >= 4:
        ch3 = prices[-1] - prices[-4]
        ups, downs = streak(prices)
        if ch3 >= 4 and ups >= 3:
            score += 3
            reasons.append(f"{_days(ups)} 연속 올랐어요 (최근 3일 {ch3:+.1f}원)")
        elif ch3 >= 3 and ups >= 2:
            score += 2
            reasons.append(f"{_days(ups)} 연속 올랐어요 (최근 3일 {ch3:+.1f}원)")
        elif ch3 >= 1:
            score += 1
            reasons.append(f"최근 3일간 {ch3:+.1f}원 올랐어요")
        elif ch3 <= -4 and downs >= 3:
            score -= 3
            reasons.append(f"{_days(downs)} 연속 내렸어요 (최근 3일 {ch3:+.1f}원)")
        elif ch3 <= -3 and downs >= 2:
            score -= 2
            reasons.append(f"{_days(downs)} 연속 내렸어요 (최근 3일 {ch3:+.1f}원)")
        elif ch3 <= -1:
            score -= 1
            reasons.append(f"최근 3일간 {ch3:+.1f}원 내렸어요")
        else:
            reasons.append(f"최근 3일 변동이 1원 안팎이에요 ({ch3:+.1f}원)")

    # 2) 주간 평균 변화
    weeks = weekly_means(daily)
    if len(weeks) >= 2:
        wch = weeks[-1][1] - weeks[-2][1]
        if wch >= 5:
            score += 1
            reasons.append(f"지난주보다 주간 평균이 {wch:+.1f}원 올랐어요")
        elif wch <= -5:
            score -= 1
            reasons.append(f"지난주보다 주간 평균이 {wch:+.1f}원 내렸어요")

    # 3) 한국석유공사 다음 주 전망 (매주 토요일 발표를 운영자가 입력, 8일 지나면 무시)
    outlook = events.get("outlook") or {}
    direction = outlook.get("direction")
    published = outlook.get("published")
    if direction in ("up", "down", "flat") and published:
        age = (today - _d(published)).days
        if 0 <= age <= 8:
            src = outlook.get("source") or "한국석유공사"
            if direction == "up":
                score += 2
                reasons.append(f"{src}: 다음 주 상승 전망")
            elif direction == "down":
                score -= 2
                reasons.append(f"{src}: 다음 주 하락 전망")
            else:
                reasons.append(f"{src}: 다음 주 보합 전망")

    level = "red" if score >= 3 else "green" if score <= -3 else "yellow"
    lean = "up" if score > 0 else "down" if score < 0 else "flat"

    # 4) 유류세 인하 일정
    tax = events.get("tax_cut") or {}
    end = tax.get("end_date")
    status = tax.get("status")
    if end:
        days_left = (_d(end) - today).days
        won = tax.get("won_per_liter", {}).get(product_name)
        if status == "ending" and days_left >= 0:
            level = "red"
            msg = f"{_d(end).month}월 {_d(end).day}일 유류세 인하 종료 확정"
            if won:
                msg += f" — 이후 리터당 최대 {won}원 오를 수 있어요"
            reasons.insert(0, msg)
        elif status == "pending" and 0 <= days_left <= 14:
            if level == "green":
                level = "yellow"
                capped_by_tax = True
            reasons.append(f"유류세 인하가 {days_left}일 뒤 끝나요 (연장 여부 미정)")

    title, subtitle = LEVEL_TEXT[level], LEVEL_SUB[level]
    if capped_by_tax:
        title, subtitle = "기다리기엔 애매해요", "유류세 인하 연장 여부가 곧 결정돼요"
    elif level == "yellow" and lean == "up":
        subtitle = "오를 조짐이 보여요"
    elif level == "yellow" and lean == "down":
        subtitle = "내릴 조짐이 보여요"

    return {
        "level": level,
        "lean": lean,
        "title": title,
        "subtitle": subtitle,
        "score": score,
        "reasons": reasons[:4],
    }


def _days(n: int) -> str:
    return "일주일 넘게" if n >= 7 else f"{n}일"


def tax_card(events: dict, today: date) -> dict | None:
    tax = events.get("tax_cut") or {}
    end = tax.get("end_date")
    if not end:
        return None
    days_left = (_d(end) - today).days
    status = tax.get("status", "pending")
    won = tax.get("won_per_liter", {})
    e = _d(end)
    if status == "extended":
        text = f"유류세 인하가 연장됐어요 ({tax.get('extended_to', '')}까지)"
    elif status == "ending":
        text = f"{e.month}월 {e.day}일 유류세 인하가 끝나요"
    else:
        text = f"유류세 인하 {e.month}월 {e.day}일까지 · 연장 여부 미정"
    return {
        "end_date": end,
        "days_left": days_left,
        "status": status,
        "text": text,
        "won_per_liter": won,
        "rates": tax.get("rates"),
    }


# 토스 스마트 발송 템플릿 규칙: 제목 7자 이하 명사형·마침표 없음, 본문 25자 이하 해요체·마침표, 기능성 정보만
PUSH_TEMPLATES = {
    ("휘발유", "red"): ("휘발유 신호", "휘발유값이 오를 전망이에요."),
    ("휘발유", "green"): ("휘발유 신호", "휘발유값이 내리는 중이에요."),
    ("경유", "red"): ("경유 신호", "경유값이 오를 전망이에요."),
    ("경유", "green"): ("경유 신호", "경유값이 내리는 중이에요."),
}


def push_suggestions(prev: dict, now: dict, tax: dict | None) -> list[dict]:
    """신호가 바뀐 경우에만 보낼 알림 문구 제안."""
    out = []
    for name, sig in now.items():
        before = (prev.get(name) or {}).get("level")
        if before and before != sig["level"] and (name, sig["level"]) in PUSH_TEMPLATES:
            title, body = PUSH_TEMPLATES[(name, sig["level"])]
            out.append({"product": name, "from": before, "to": sig["level"], "title": title, "body": body})
    if tax and tax["status"] == "ending" and 0 <= tax["days_left"] <= 7:
        out.append({"product": "공통", "from": None, "to": "red", "title": "유류세 마감",
                    "body": f"유류세 인하가 {tax['days_left']}일 뒤 끝나요." if tax["days_left"] else "오늘 유류세 인하가 끝나요."})
    # 글자 수 규칙을 넘는 문구는 내보내지 않음 (수집이 멈추지 않도록 예외 대신 걸러냄)
    return [m for m in out if len(m["title"]) <= 7 and len(m["body"]) <= 25]
