import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const mapAsset = new URL("../public/media/shuttle/changi-reference-route-map.png", import.meta.url);

test("static shuttle map is rendered beside the camera stage with accessible text", () => {
  assert.match(html, /class="video-content"[\s\S]*class="video-grid" id="videoGrid"/);
  assert.match(html, /class="shuttle-map-card" aria-label="接驳车位置示意图"/);
  assert.match(html, /src="\.\/public\/media\/shuttle\/changi-reference-route-map\.png"/);
  assert.match(html, /alt="樟宜机场行政地图接驳路线示意图，接驳车 05 位于机场中央区域"/);
  assert.match(html, />\s*车辆位置示意\s*</);
  assert.ok(existsSync(mapAsset), "static shuttle map asset should exist");
});

test("shuttle map remains decorative and has no JavaScript interaction", () => {
  assert.doesNotMatch(html, /shuttle-map-card[^>]*(?:data-|tabindex|role="button")/);
  assert.doesNotMatch(appSource, /shuttleMap|shuttle-map|changi-reference-route-map/);
});

test("shuttle map fills the desktop column and moves below video on narrow screens", () => {
  assert.match(styles, /\.shuttle-map-image\s*\{[^}]*position:\s*absolute;[^}]*width:\s*100%;[^}]*height:\s*100%;[^}]*object-fit:\s*cover;/s);
  assert.match(
    styles,
    /@media\s*\(max-width:\s*900px\)[\s\S]*?\.shuttle-map-card\s*\{[^}]*min-height:\s*220px;[^}]*aspect-ratio:\s*16\s*\/\s*7;/s
  );
});
