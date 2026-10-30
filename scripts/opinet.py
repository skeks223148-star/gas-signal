"""오피넷 일반 API 클라이언트.

- 하루 호출 한도(현재 300회)를 넘지 않도록 호출 수를 세고, 예산을 넘으면 멈춘다.
- FIXTURE_DIR 환경변수가 있으면 실제 호출 대신 그 폴더의 샘플 응답을 읽는다(테스트용).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.opinet.co.kr/api/"

# 제품 코드
GASOLINE = "B027"   # 보통휘발유
PREMIUM = "B034"    # 고급휘발유
DIESEL = "D047"     # 자동차용경유
KEROSENE = "C004"   # 실내등유
LPG = "K015"        # 자동차용부탄

PRODUCT_NAMES = {
    GASOLINE: "휘발유",
    PREMIUM: "고급휘발유",
    DIESEL: "경유",
    KEROSENE: "등유",
    LPG: "LPG",
}

BRAND_NAMES = {
    "SKE": "SK에너지",
    "GSC": "GS칼텍스",
    "HDO": "HD현대오일뱅크",
    "SOL": "S-OIL",
    "RTO": "알뜰주유소",
    "RTX": "알뜰(고속도로)",
    "NHO": "NH-OIL",
    "SKG": "SK가스",
    "E1G": "E1",
    "ETC": "자가상표",
}


class OpinetError(RuntimeError):
    pass


class BudgetExceeded(OpinetError):
    pass


class Opinet:
    def __init__(self, key: str | None, budget: int, fixture_dir: str | None = None):
        self.key = key
        self.budget = budget          # 이번 실행에서 쓸 수 있는 최대 호출 수
        self.calls = 0
        self.fixture_dir = fixture_dir
        self.log: list[str] = []

    def _fixture(self, endpoint: str, params: dict) -> dict:
        # 예: avgSigunPrice__sido=02.json → 없으면 avgSigunPrice.json
        keys = [k for k in ("sido", "area", "prodcd", "date") if k in params]
        specific = endpoint + "".join(f"__{k}={params[k]}" for k in keys) + ".json"
        for name in (specific, endpoint + ".json"):
            path = os.path.join(self.fixture_dir, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        return {"RESULT": {"OIL": []}}

    def get(self, endpoint: str, **params) -> list[dict]:
        if self.calls >= self.budget:
            raise BudgetExceeded(f"호출 예산 {self.budget}회 도달 — {endpoint} 건너뜀")
        self.calls += 1
        self.log.append(endpoint + " " + json.dumps(params, ensure_ascii=False))

        if self.fixture_dir:
            data = self._fixture(endpoint, params)
        else:
            if not self.key:
                raise OpinetError("OPINET_KEY 가 설정되지 않았어요")
            query = urllib.parse.urlencode({"code": self.key, "out": "json", **params})
            url = f"{BASE}{endpoint}.do?{query}"
            data = self._fetch(url)

        oil = (data.get("RESULT") or {}).get("OIL", [])
        if isinstance(oil, dict):
            oil = [oil]
        return oil

    @staticmethod
    def _fetch(url: str) -> dict:
        last_err = None
        for attempt in range(2):  # 네트워크 오류일 때만 1번 더 시도
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "gas-signal/1.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    # 키 오류·한도 초과 시 오피넷이 JSON이 아닌 안내문을 돌려줄 수 있음
                    raise OpinetError("오피넷 응답이 JSON이 아니에요: " + raw[:200])
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                time.sleep(3)
        raise OpinetError(f"오피넷 접속 실패: {last_err}")


def to_float(v) -> float | None:
    try:
        return round(float(str(v).strip()), 2)
    except (TypeError, ValueError):
        return None
