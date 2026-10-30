"""미니앱 화면을 일반 브라우저에서 볼 수 있는 파일 하나로 묶는다 (토스 SDK 대신 흉내 함수 사용).

python3 tests/build_preview.py <출력.html> [기본 시도코드] [기본 시군구코드]
실시간 데이터를 못 불러오면 저장소의 docs/data 스냅샷을 대신 보여준다.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "app", "src")
DATA = os.path.join(ROOT, "docs", "data")
out = sys.argv[1]
default_sido = sys.argv[2] if len(sys.argv) > 2 else ""
default_sigun = sys.argv[3] if len(sys.argv) > 3 else ""


def read(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return f.read()


def strip_module(js):
    js = re.sub(r'^import[^;]*;\s*$', "", js, flags=re.M)
    js = re.sub(r"^export\s+", "", js, flags=re.M)
    return js


snapshot = {}
for name in ("latest.json", "regions.json"):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        snapshot[name] = json.load(f)
for fn in os.listdir(os.path.join(DATA, "region")):
    with open(os.path.join(DATA, "region", fn), encoding="utf-8") as f:
        snapshot["region/" + fn] = json.load(f)

stub = """
// 미리보기용 SDK 흉내
async function storageGet(k){ try { return localStorage.getItem(k); } catch { return null; } }
async function storageSet(k,v){ try { localStorage.setItem(k,v); } catch {} }
async function openURL(u){ window.open(u, "_blank"); }
async function shareApp(t){ try { if (navigator.share) { await navigator.share({ text: t }); return true; } } catch {} alert(t); return false; }
function requestAlerts(){ return Promise.resolve("newAgreement"); }
function attachBanner(){}
function preloadFullAd(){}
function showFullAd(){ return Promise.resolve(false); }
"""

main = strip_module(read("main.js"))
main = main.replace('throw lastErr || new Error("load failed");',
                    'if (window.__SNAPSHOT__ && window.__SNAPSHOT__[path]) return window.__SNAPSHOT__[path];\n  throw lastErr || new Error("load failed");')
if default_sido:
    main = main.replace("  try {\n    state.latest = await fetchJSON",
                        f'  if (!state.sido) {{ state.sido = "{default_sido}"; state.sigun = "{default_sigun}" || null; }}\n  try {{\n    state.latest = await fetchJSON', 1)

config = strip_module(read("config.js")).replace('ALERT_TEMPLATE_CODE = ""', 'ALERT_TEMPLATE_CODE = "preview"')

html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>기름값 신호등 미리보기</title>
<style>{read("style.css")}</style></head>
<body><div id="app"><div class="loading">기름값을 불러오는 중이에요</div></div>
<script>window.__SNAPSHOT__ = {json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))};</script>
<script type="module">
{config}
{stub}
{strip_module(read("view.js"))}
{main}
</script></body></html>"""
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(out, len(html) // 1024, "KB")
