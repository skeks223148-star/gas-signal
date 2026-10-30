import "./style.css";
import { AD_BANNER_ID, AD_INTERSTITIAL_ID, ALERT_TEMPLATE_CODE, DATA_URLS, TANK_LITERS } from "./config.js";
import { attachBanner, openURL, preloadFullAd, requestAlerts, shareApp, showFullAd, storageGet, storageSet } from "./sdk.js";
import {
  actionsCard, footer, header, lowestCard, priceCard, regionSheet, shortRegion, signalCard, taxCard, trendCard,
} from "./view.js";

const app = document.getElementById("app");

const state = {
  latest: null,
  index: null,       // regions.json
  region: null,      // region/<시도>.json
  product: "휘발유",
  sido: null,        // "02"
  sigun: null,       // "0236"
  sheet: null,       // null | "list" | "<시도코드>"
  unlocked: !AD_INTERSTITIAL_ID,
  alerts: null,
};

// ---------- 데이터 ----------
const bucket = () => Math.floor(Date.now() / 600000); // 10분 단위 캐시

async function fetchJSON(path) {
  let lastErr;
  for (const base of DATA_URLS) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 8000);
      const res = await fetch(`${base}${path}?t=${bucket()}`, { signal: ctrl.signal, cache: "no-store" });
      clearTimeout(t);
      if (res.ok) return await res.json();
      lastErr = new Error(String(res.status));
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("load failed");
}

async function loadRegion() {
  state.region = null;
  if (!state.sido) return;
  try {
    state.region = await fetchJSON(`region/${state.sido}.json`);
  } catch {
    state.region = null;
  }
}

// ---------- 화면 ----------
function currentItems() {
  const sidoItem = state.latest?.sido?.find((s) => s.code === state.sido) || null;
  const sigunItem = state.region?.sigun?.find((g) => g.code === state.sigun) || null;
  return { sidoItem, sigunItem };
}

function lowestData() {
  const r = state.region;
  const p = state.product;
  if (!r) return { stations: null };
  const { sidoItem, sigunItem } = currentItems();
  const bySigun = state.sigun && r.lowest_sigun?.[state.sigun]?.[p];
  if (bySigun && bySigun.length) {
    return { stations: bySigun, title: `${shortRegion(sigunItem?.name)} 최저가 주유소`, avg: sigunItem?.[p]?.price };
  }
  return { stations: r.lowest?.[p] || [], title: `${r.name} 최저가 주유소`, avg: sidoItem?.[p]?.price };
}

function regionLabel() {
  const { sidoItem, sigunItem } = currentItems();
  if (sigunItem) return sigunItem.name;
  if (sidoItem) return sidoItem.name;
  return null;
}

function render() {
  const L = state.latest;
  const p = state.product;
  const { sidoItem, sigunItem } = currentItems();
  const low = lowestData();
  app.innerHTML = `
    ${header({ regionLabel: regionLabel(), product: p })}
    ${signalCard(L?.signal?.[p], p, L)}
    ${priceCard({ product: p, latest: L, sidoItem, sigunItem, regionName: regionLabel() })}
    ${lowestCard({ product: p, ...low, locked: !state.unlocked, tankLiters: TANK_LITERS })}
    ${taxCard(L?.tax_cut, p)}
    ${trendCard(L?.trend?.[p], p)}
    ${actionsCard({ alertsEnabled: !!ALERT_TEMPLATE_CODE, alertsState: state.alerts })}
    <div id="banner" class="banner" ${AD_BANNER_ID ? "" : 'style="display:none"'}></div>
    ${footer(L)}
    ${state.sheet ? regionSheet(state.index, state.sheet === "list" ? null : state.sheet) : ""}
  `;
}

// ---------- 동작 ----------
async function selectRegion(sido, sigun) {
  state.sido = sido;
  state.sigun = sigun || null;
  state.sheet = null;
  await storageSet("region", JSON.stringify({ sido: state.sido, sigun: state.sigun }));
  render();
  await loadRegion();
  render();
}

app.addEventListener("click", async (e) => {
  const t = e.target.closest("button");
  if (!t) return;

  if (t.dataset.product) {
    state.product = t.dataset.product;
    storageSet("product", state.product);
    return render();
  }
  if (t.id === "pick-region" || t.id === "pick-region-2") {
    if (!state.index) {
      try { state.index = await fetchJSON("regions.json"); } catch { return; }
    }
    state.sheet = "list";
    return render();
  }
  if (t.id === "close-sheet") { state.sheet = null; return render(); }
  if (t.id === "back-sheet") { state.sheet = "list"; return render(); }
  if (t.dataset.sido) {
    state.sheet = t.dataset.sido;
    return render();
  }
  if (t.dataset.sido2 !== undefined) {
    return selectRegion(t.dataset.sido2, t.dataset.sigun || null);
  }
  if (t.id === "unlock-lowest") {
    t.disabled = true;
    await showFullAd(AD_INTERSTITIAL_ID);
    state.unlocked = true;         // 광고가 없거나 실패해도 결과는 보여줘요
    preloadFullAd(AD_INTERSTITIAL_ID);
    return render();
  }
  if (t.dataset.map) {
    return openURL(`https://map.kakao.com/link/search/${encodeURIComponent(t.dataset.map)}`);
  }
  if (t.id === "alerts") {
    const r = await requestAlerts(ALERT_TEMPLATE_CODE);
    if (r === "newAgreement" || r === "alreadyAgreed") state.alerts = "on";
    return render();
  }
  if (t.id === "share") {
    const sig = state.latest?.signal?.[state.product];
    const msg = sig ? `오늘 ${state.product} 신호: ${sig.title}` : "기름값 신호등";
    return shareApp(`${msg} — 넣기 전에 확인해 보세요`);
  }
});

async function start() {
  try {
    const saved = await storageGet("region");
    if (saved) {
      const r = JSON.parse(saved);
      state.sido = r.sido || null;
      state.sigun = r.sigun || null;
    }
    const prod = await storageGet("product");
    if (prod === "휘발유" || prod === "경유") state.product = prod;
  } catch { /* 저장값 없음 */ }

  try {
    state.latest = await fetchJSON("latest.json");
  } catch {
    app.innerHTML = `<div class="loading">기름값을 불러오지 못했어요.<br><button class="secondary" onclick="location.reload()">다시 시도</button></div>`;
    return;
  }
  render();
  await loadRegion();
  render();
  attachBanner(AD_BANNER_ID, "#banner");
  preloadFullAd(AD_INTERSTITIAL_ID);
}

start();
