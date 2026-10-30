import { defineConfig } from "@apps-in-toss/web-framework/config";

export default defineConfig({
  // 콘솔에 등록하는 영문 앱 이름과 반드시 같아야 해요 (등록 후 변경 불가)
  appName: "gas-signal",
  brand: { primaryColor: "#3182F6" },
  webView: {},
  permissions: [],
  webBundleDir: "dist",
});
