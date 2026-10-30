// 앱인토스 SDK 호출은 전부 이 파일에서만 해요.
// 토스 앱 밖(일반 브라우저 미리보기)에서는 기본 브라우저 기능으로 대신해요.
import { Device, Notification, Share, Storage, TossAds, loadFullScreenAd, showFullScreenAd } from "@apps-in-toss/web-framework";
import { APP_NAME } from "./config.js";

const supported = (fn) => {
  try {
    return typeof fn === "function" && (typeof fn.isSupported !== "function" || fn.isSupported());
  } catch {
    return false;
  }
};

export async function storageGet(key) {
  try {
    if (Storage && supported(Storage.getItem)) return await Storage.getItem(key);
  } catch { /* 아래로 */ }
  try { return localStorage.getItem(key); } catch { return null; }
}

export async function storageSet(key, value) {
  try {
    if (Storage && supported(Storage.setItem)) return await Storage.setItem(key, value);
  } catch { /* 아래로 */ }
  try { localStorage.setItem(key, value); } catch { /* 저장 못 해도 앱은 계속 동작 */ }
}

export async function openURL(url) {
  try {
    if (Device && supported(Device.openURL)) return await Device.openURL(url);
  } catch { /* 아래로 */ }
  window.open(url, "_blank");
}

export async function shareApp(text) {
  try {
    if (Share && supported(Share.createLink) && supported(Share.sendMessage)) {
      const link = await Share.createLink({ path: `intoss://${APP_NAME}` });
      await Share.sendMessage({ message: `${text}\n${link}` });
      return true;
    }
  } catch { /* 아래로 */ }
  try {
    if (navigator.share) { await navigator.share({ text }); return true; }
  } catch { /* 취소 */ }
  return false;
}

// 알림 동의: 사용자가 버튼을 눌렀을 때만 호출 (진입하자마자 띄우면 검수 탈락)
export function requestAlerts(templateCode) {
  return new Promise((resolve) => {
    try {
      if (!templateCode || !Notification || !supported(Notification.requestAgreement)) return resolve("unsupported");
      const cleanup = Notification.requestAgreement({
        options: { templateCode },
        onEvent: (r) => { try { cleanup && cleanup(); } catch {} resolve(r && r.type); },
        onError: () => { try { cleanup && cleanup(); } catch {} resolve("error"); },
      });
    } catch {
      resolve("error");
    }
  });
}

// 배너 광고: 스크롤 화면 맨 아래 1개만
export function attachBanner(adGroupId, selector) {
  try {
    if (!adGroupId || !TossAds || !supported(TossAds.initialize)) return;
    TossAds.initialize({
      callbacks: {
        onInitialized: () => {
          try {
            TossAds.attachBanner(adGroupId, selector, {
              theme: "auto", tone: "blackAndWhite", variant: "expanded",
              callbacks: { onNoFill: () => hide(selector), onAdFailedToRender: () => hide(selector) },
            });
          } catch { hide(selector); }
        },
        onInitializationFailed: () => hide(selector),
      },
    });
  } catch { hide(selector); }
}

function hide(selector) {
  const el = document.querySelector(selector);
  if (el) el.style.display = "none";
}

// 전면 광고: 화면 진입 때 미리 불러두고, 결과를 보여주기 직전에 1번만
let fullAdReady = false;
export function preloadFullAd(adGroupId) {
  try {
    if (!adGroupId || !supported(loadFullScreenAd)) return;
    loadFullScreenAd({
      options: { adGroupId },
      onEvent: (e) => { if (e && e.type === "loaded") fullAdReady = true; },
      onError: () => { fullAdReady = false; },
    });
  } catch { /* 광고 없이 진행 */ }
}

export function showFullAd(adGroupId) {
  return new Promise((resolve) => {
    if (!adGroupId || !fullAdReady || !supported(showFullScreenAd)) return resolve(false);
    let done = false;
    const finish = (v) => { if (!done) { done = true; fullAdReady = false; resolve(v); } };
    try {
      showFullScreenAd({
        options: { adGroupId },
        onEvent: (e) => { if (e && (e.type === "dismissed" || e.type === "failedToShow")) finish(true); },
        onError: () => finish(false),
      });
      setTimeout(() => finish(false), 60000);
    } catch {
      finish(false);
    }
  });
}
