#!/usr/bin/env bash
# 샘플 응답으로 여러 상황을 돌려보는 점검 스크립트 (오피넷 호출 없음)
# 사용: bash tests/run_scenarios.sh <작업폴더>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="${1:?작업폴더}"
rm -rf "$W" && mkdir -p "$W"

fresh() {  # 새 실행 폴더 준비
  rm -rf "$W/$1" && mkdir -p "$W/$1" && cp -r "$ROOT/scripts" "$ROOT/config" "$W/$1/"
}
run() {  # run <폴더> <시나리오> <날짜> <모드>
  python3 "$ROOT/tests/make_fixtures.py" "$W/fx_$2_$3" "$2" "$3" >/dev/null
  (cd "$W/$1" && FIXTURE_DIR="$W/fx_$2_$3" NOW_KST="${3}T${5:-00:40}" python3 scripts/update.py --mode "$4")
}
setjson() {  # setjson <파일> <파이썬식>
  python3 - "$1" "$2" <<'PY'
import json, sys
p, expr = sys.argv[1], sys.argv[2]
d = json.load(open(p, encoding="utf-8"))
exec(expr)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
}

echo "### 1) 하락장 → 초록"
fresh a; run a down 2026-10-31 full

echo; echo "### 2) 보합 다음 날 상승 전환 → 노랑에서 빨강, 알림 제안"
fresh b; run b flat 2026-10-30 full; run b up 2026-10-31 full

echo; echo "### 3) 같은 날 light / weekly 실행 (호출 2회 / 3회)"
run b up 2026-10-31 light 09:10
run b up 2026-10-31 weekly 10:25

echo; echo "### 4) 유류세 마감 10일 전, 하락장 → 초록 대신 노랑"
fresh c; run c down 2026-11-20 full

echo; echo "### 5) 유류세 종료 확정 → 무조건 빨강 + 마감 임박 알림"
fresh d; setjson "$W/d/config/events.json" "d['tax_cut']['status']='ending'"
run d down 2026-11-25 full

echo; echo "### 6) 보합 + 석유공사 '다음 주 상승' 전망 → 노랑(오를 조짐)"
fresh e; setjson "$W/e/config/events.json" "d['outlook'].update(direction='up', published='2026-10-31')"
run e flat 2026-10-31 full

echo; echo "### 7) 오늘 한도 소진 시 실행 안 함"
mkdir -p "$W/e/state"; setjson "$W/e/state/state.json" "d['calls']['2026-10-31']=279"
run e flat 2026-10-31 light 12:10
