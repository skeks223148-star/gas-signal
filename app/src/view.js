// 화면 조각을 만드는 순수 함수들 (DOM 없이 테스트 가능)

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const won = (n) => (n == null || isNaN(n) ? "-" : Math.round(n).toLocaleString("ko-KR") + "원");

export const signedWon = (n, digits = 1) => {
  if (n == null || isNaN(n)) return "";
  const v = Number(n).toFixed(digits);
  if (Number(v) === 0) return "어제와 같아요";
  return (n > 0 ? "▲ " : "▼ ") + Math.abs(Number(v)).toLocaleString("ko-KR") + "원";
};

const dateText = (yyyymmdd) => {
  const s = String(yyyymmdd || "");
  return s.length === 8 ? `${Number(s.slice(4, 6))}.${Number(s.slice(6, 8))}` : s;
};

export const updatedText = (iso) => {
  if (!iso) return "";
  const m = String(iso).match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  return m ? `${Number(m[2])}월 ${Number(m[3])}일 ${m[4]}:${m[5]}` : iso;
};

export const shortRegion = (name) => String(name || "").replace(/^(서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|전남광주)\s+/, "");

export function header({ regionLabel, product }) {
  const tab = (p) => `<button class="seg ${p === product ? "on" : ""}" data-product="${p}">${p}</button>`;
  return `
  <div class="top">
    <button class="chip" id="pick-region"><span class="pin"></span>${esc(regionLabel || "내 지역 설정")}<span class="caret"></span></button>
    <div class="segs">${tab("휘발유")}${tab("경유")}</div>
  </div>`;
}

export function signalCard(sig, product, latest) {
  if (!sig) return `<section class="card"><p class="muted">신호를 계산하는 중이에요.</p></section>`;
  const lights = ["red", "yellow", "green"]
    .map((c) => `<span class="lamp ${c} ${sig.level === c ? "on" : ""}"></span>`).join("");
  const reasons = (sig.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("");
  const last = (latest?.trend?.[product] || []).slice(-1)[0];
  return `
  <section class="card hero ${esc(sig.level)}">
    <div class="lamps" aria-hidden="true">${lights}</div>
    <p class="eyebrow">${esc(product)} 신호등</p>
    <h1>${esc(sig.title)}</h1>
    <p class="sub">${esc(sig.subtitle)}</p>
    ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
    <p class="fine">${last ? `${dateText(last.date)}까지 확정된 전국 평균 기준 · ` : ""}전망은 참고용이에요</p>
  </section>`;
}

export function priceCard({ product, latest, sidoItem, sigunItem, regionName }) {
  const nat = latest?.national?.[product];
  const sido = sidoItem?.[product];
  const sigun = sigunItem?.[product];
  const main = sigun || sido || nat;
  const mainLabel = sigun ? `${shortRegion(sigunItem.name)} 평균` : sido ? `${sidoItem.name} 평균` : "전국 평균";
  const row = (label, v) => (v ? `<div class="row"><span>${esc(label)}</span><span><b>${won(v.price)}</b> <em class="${v.diff > 0 ? "up" : v.diff < 0 ? "down" : ""}">${signedWon(v.diff)}</em></span></div>` : "");
  return `
  <section class="card">
    <p class="label">${esc(mainLabel)} · ${esc(product)}</p>
    <p class="big">${won(main?.price)}</p>
    <p class="diff ${main?.diff > 0 ? "up" : main?.diff < 0 ? "down" : ""}">${main ? signedWon(main.diff) : ""}</p>
    <div class="rows">
      ${sigun ? row(`${sidoItem?.name || ""} 평균`, sido) : ""}
      ${main !== nat ? row("전국 평균", nat) : ""}
    </div>
    ${regionName ? "" : `<button class="link" id="pick-region-2">우리 동네 가격 보기</button>`}
  </section>`;
}

export function lowestCard({ product, stations, title, avg, locked, tankLiters }) {
  if (!stations) return "";
  if (!stations.length) return `<section class="card"><p class="label">${esc(title)}</p><p class="muted">아직 최저가 정보가 없어요.</p></section>`;
  if (locked) {
    return `
    <section class="card">
      <p class="label">${esc(title)}</p>
      <button class="primary" id="unlock-lowest">최저가 주유소 ${Math.min(stations.length, 5)}곳 보기</button>
      <p class="fine center">광고를 한 번 본 뒤 보여드려요</p>
    </section>`;
  }
  const items = stations.slice(0, 5).map((s, i) => {
    const save = avg && s.price ? Math.round((avg - s.price) * tankLiters) : 0;
    return `
    <li class="station">
      <span class="rank">${i + 1}</span>
      <div class="info">
        <b>${esc(s.name)}</b>
        <span class="muted">${esc(s.brand)} · ${esc(s.address)}</span>
        ${save > 0 ? `<span class="save">평균보다 ${tankLiters}L에 ${save.toLocaleString("ko-KR")}원 아껴요</span>` : ""}
      </div>
      <div class="right">
        <b>${won(s.price)}</b>
        <button class="map" data-map="${esc(s.name + " " + s.address)}">길찾기</button>
      </div>
    </li>`;
  }).join("");
  return `<section class="card"><p class="label">${esc(title)}</p><ul class="stations">${items}</ul></section>`;
}

export function trendCard(series, product) {
  if (!series || series.length < 2) return "";
  const W = 320, H = 96, P = 8;
  const ps = series.map((x) => x.price);
  const min = Math.min(...ps), max = Math.max(...ps);
  const span = Math.max(max - min, 1);
  const pts = series.map((x, i) => {
    const xx = P + (i * (W - 2 * P)) / (series.length - 1);
    const yy = P + (H - 2 * P) * (1 - (x.price - min) / span);
    return `${xx.toFixed(1)},${yy.toFixed(1)}`;
  });
  const first = series[0], last = series[series.length - 1];
  const change = last.price - first.price;
  return `
  <section class="card">
    <p class="label">최근 ${series.length}일 전국 평균 · ${esc(product)}</p>
    <p class="trend-head">${Math.abs(change) < 0.5 ? "거의 그대로예요" : change > 0 ? `${Math.abs(change).toFixed(1)}원 올랐어요` : `${Math.abs(change).toFixed(1)}원 내렸어요`}</p>
    <svg viewBox="0 0 ${W} ${H}" class="spark" role="img" aria-label="최근 가격 추이">
      <polyline points="${pts.join(" ")}" fill="none" stroke="#3182F6" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${pts[pts.length - 1].split(",")[0]}" cy="${pts[pts.length - 1].split(",")[1]}" r="4" fill="#3182F6"/>
    </svg>
    <div class="axis"><span>${dateText(first.date)} ${won(first.price)}</span><span>${dateText(last.date)} ${won(last.price)}</span></div>
  </section>`;
}

export function taxCard(tax, product) {
  if (!tax) return "";
  const amount = tax.won_per_liter?.[product];
  const d = tax.days_left;
  const badge = tax.status === "extended" ? "연장됨" : d >= 0 ? `D-${d}` : "종료";
  return `
  <section class="card tax ${tax.status}">
    <div class="row"><p class="label">유류세 인하</p><span class="badge">${esc(badge)}</span></div>
    <p class="tax-text">${esc(tax.text)}</p>
    ${amount && tax.status !== "extended" ? `<p class="muted">끝나면 ${esc(product)} 리터당 최대 ${amount}원 오를 수 있어요</p>` : ""}
  </section>`;
}

export function actionsCard({ alertsEnabled, alertsState }) {
  const alertBtn = alertsEnabled
    ? `<button class="primary ghost" id="alerts" ${alertsState === "on" ? "disabled" : ""}>${alertsState === "on" ? "신호가 바뀌면 알려드릴게요" : "신호가 바뀌면 알림 받기"}</button>`
    : "";
  return `
  <section class="actions">
    ${alertBtn}
    <button class="secondary" id="share">친구에게 알려주기</button>
  </section>`;
}

export function footer(latest) {
  return `
  <footer>
    <p>자료: ${esc(latest?.source || "한국석유공사 오피넷")} · ${esc(updatedText(latest?.updated_at))} 갱신</p>
    <p>가격 전망은 참고용이며 실제 가격과 다를 수 있어요.</p>
  </footer>`;
}

export function regionSheet(index, step) {
  if (!index) return "";
  if (!step) {
    const items = index.sido.map((s) => `<button class="opt" data-sido="${esc(s.code)}">${esc(s.name)}</button>`).join("");
    return `<div class="sheet"><div class="sheet-head"><b>지역을 골라주세요</b><button class="x" id="close-sheet">닫기</button></div><div class="grid">${items}</div></div>`;
  }
  const sido = index.sido.find((s) => s.code === step);
  const items = [`<button class="opt" data-sigun="" data-sido2="${esc(step)}">${esc(sido.name)} 전체</button>`]
    .concat(sido.sigun.map((g) => `<button class="opt" data-sigun="${esc(g.code)}" data-sido2="${esc(step)}">${esc(shortRegion(g.name))}</button>`))
    .join("");
  return `<div class="sheet"><div class="sheet-head"><button class="x" id="back-sheet">다른 시도</button><b>${esc(sido.name)}</b><button class="x" id="close-sheet">닫기</button></div><div class="grid">${items}</div></div>`;
}
