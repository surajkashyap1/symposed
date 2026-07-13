// Screenshot helper: node /tmp/shot.mjs <url> <outfile> [width] [height] [fullpage]
import { chromium } from "@playwright/test";
const [url, out, w = "1280", h = "800", full = ""] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: +w, height: +h },
  deviceScaleFactor: 1,
});
await page.goto(url, { waitUntil: "networkidle" });
await page.waitForTimeout(400);
await page.screenshot({ path: out, fullPage: full === "full" });
await browser.close();
console.log("saved", out);
