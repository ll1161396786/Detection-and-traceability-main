import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const liveStyles = readFileSync(new URL("../live-monitor.css", import.meta.url), "utf8");

test("video section contains only the full-width camera wall", () => {
  assert.match(html, /class="video-content"\s*>\s*<div class="video-grid" id="videoGrid"><\/div>\s*<\/div>/);
  assert.doesNotMatch(html, /shuttle-map|车辆位置示意|changi-reference-route-map/);
  assert.doesNotMatch(styles, /\.shuttle-map-/);
});

test("HD frames fit the full main stage without intrinsic-size cropping", () => {
  assert.match(liveStyles, /\.live-frame\s*\{[^}]*position:\s*absolute;[^}]*width:\s*100%;[^}]*height:\s*100%;[^}]*object-fit:\s*contain;/s);
  assert.match(styles, /\.cam-main\s*\{[^}]*max-height:/s);
});

test("narrow screens retain a complete proportional main picture", () => {
  assert.match(styles, /@media\s*\(max-width:\s*900px\)[\s\S]*?\.cam-main\s*\{\s*max-height:\s*none;/s);
});
