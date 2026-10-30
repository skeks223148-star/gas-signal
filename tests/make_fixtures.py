"""오피넷 이용 가이드(2026.10)의 응답 형식대로 샘플 응답을 만든다.

python tests/make_fixtures.py <폴더> <시나리오: down|up|flat> <기준일 YYYY-MM-DD>
"""
import json
import os
import sys
from datetime import date, timedelta

out, scenario, base = sys.argv[1], sys.argv[2], date.fromisoformat(sys.argv[3])
os.makedirs(out, exist_ok=True)

step = {"down": -1.4, "up": 1.6, "flat": 0.1}[scenario]


def price(prod, d):
    # 기준일(어제)까지 30일 시계열
    days = (base - timedelta(days=1) - d).days
    start = {"B027": 1856.6, "D047": 1842.8, "B034": 2105.3, "K015": 1050.2}[prod]
    if scenario == "up":
        # 그동안 조금씩 내리다가 최근 4일 연속 오르는 상황
        if days >= 4:
            return round(start + 0.2 * (days - 4), 2)
        return round(start + step * (4 - days), 2)
    return round(start - step * days, 2)


def write(name, rows):
    with open(os.path.join(out, name), "w", encoding="utf-8") as f:
        json.dump({"RESULT": {"OIL": rows}}, f, ensure_ascii=False)


prods = ["B027", "D047", "B034", "K015"]
yday = base - timedelta(days=1)

write("avgAllPrice.json", [
    {"TRADE_DT": base.strftime("%Y%m%d"), "PRODCD": p, "PRODNM": p,
     "PRICE": str(price(p, yday) + step / 2), "DIFF": str(round(step / 2, 2))} for p in prods])

write("avgRecentPrice.json", [
    {"DATE": (yday - timedelta(days=i)).strftime("%Y%m%d"), "PRODCD": p, "PRICE": str(price(p, yday - timedelta(days=i)))}
    for i in range(7) for p in prods])

for wb in (1, 2, 3):
    target = base - timedelta(days=7 * wb + 1)
    write(f"dateAvgRecentPrice__date={target.strftime('%Y%m%d')}.json", [
        {"DATE": (target - timedelta(days=i)).strftime("%Y%m%d"), "PRODCD": p,
         "PRICE": str(price(p, target - timedelta(days=i)))}
        for i in range(7) for p in prods])

sidos = [("01", "서울", 80), ("02", "경기", -5), ("15", "인천", -8), ("10", "부산", -12), ("11", "제주", 60)]
write("avgSidoPrice.json",
      [{"SIDOCD": "00", "SIDONM": "전국", "PRODCD": "B027", "PRICE": "1856.6", "DIFF": "-0.2"}] +
      [{"SIDOCD": c, "SIDONM": n, "PRODCD": p, "PRICE": str(price(p, yday) + off), "DIFF": str(step / 2)}
       for c, n, off in sidos for p in ("B027", "D047", "B034", "C004", "K015") if p != "C004"])

siguns = {
    "01": [("0101", "종로구"), ("0102", "중구"), ("0123", "강남구")],
    "02": [("0201", "수원시"), ("0215", "김포시"), ("0210", "고양시")],
    "15": [("1501", "중구"), ("1507", "서구")],
    "10": [("1001", "중구"), ("1016", "해운대구")],
    "11": [("1101", "제주시"), ("1102", "서귀포시")],
}
for sc, rows in siguns.items():
    write(f"avgSigunPrice__sido={sc}.json", [
        {"SIGUNCD": c, "SIGUNNM": n, "PRODCD": p, "PRICE": str(price(p, yday) + (i * 7) - 10), "DIFF": "0.00"}
        for i, (c, n) in enumerate(rows) for p in ("B027", "D047", "B034")])

write("lowTop10.json", [
    {"UNI_ID": f"A00{i:05d}", "PRICE": str(1729 + i * 3), "POLL_DIV_CD": ["RTO", "SKE", "GSC", "SOL", "HDO"][i % 5],
     "OS_NM": f"샘플{i + 1}주유소", "VAN_ADR": f"경기 김포시 샘플동 {i + 1}", "NEW_ADR": f"경기 김포시 샘플로 {i + 10}",
     "GIS_X_COOR": "290000.0", "GIS_Y_COOR": "560000.0"} for i in range(10)])

write("avgLastWeek.json", [
    {"WEEK": "2026104", "STA_DT": "20261018", "END_DT": "20261024", "AREA_CD": "00", "PRODCD": p,
     "PRICE": str(price(p, base - timedelta(days=7)))} for p in prods])
print("fixtures ->", out)
