import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

const luggageAssets = [
  "large-suitcase-v1.png",
  "cabin-suitcase-v1.png",
  "travel-backpack-v1.png",
  "duffel-bag-v1.png",
  "canvas-tote-v1.png",
  "briefcase-v1.png"
];

function readPngSize(url) {
  const bytes = readFileSync(url);
  assert.deepEqual([...bytes.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

test("common luggage catalog contains six referenced 640px PNG assets", () => {
  for (const filename of luggageAssets) {
    const size = readPngSize(new URL(`../public/media/luggage/${filename}`, import.meta.url));
    assert.deepEqual(size, { width: 640, height: 640 }, filename);
    assert.match(appSource, new RegExp(`public/media/luggage/${filename.replace(".", "\\.")}`));
  }
});

test("hazard and luggage titles precede their image tracks", () => {
  const hazardTitle = html.indexOf("<h2>危险物品库</h2>");
  const hazardTrack = html.indexOf('id="hazardGrid"');
  const luggageTitle = html.indexOf("<h2>常见物品库</h2>");
  const luggageTrack = html.indexOf('id="luggageGrid"');

  assert.ok(hazardTitle >= 0 && hazardTitle < hazardTrack);
  assert.ok(luggageTitle > hazardTrack && luggageTitle < luggageTrack);
  assert.match(html, /id="hazardGrid"[^>]*role="list"[^>]*tabindex="0"/);
  assert.match(html, /id="luggageGrid"[^>]*role="list"[^>]*tabindex="0"/);
  assert.ok(luggageTrack < html.indexOf('<main class="workspace">'));
  assert.match(styles, /\.reference-libraries\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s);
});

test("catalog tracks use double-width leading labels and remain single-row scrollers", () => {
  assert.match(
    styles,
    /\.catalog-track\s*\{[^}]*overflow-x:\s*auto;[^}]*overflow-y:\s*hidden;[^}]*grid-auto-flow:\s*column;[^}]*grid-auto-columns:\s*88px;[^}]*grid-template-rows:\s*88px;/s
  );
  assert.match(styles, /\.catalog-image\s*\{[^}]*object-fit:\s*contain;/s);
  assert.match(styles, /\.catalog-row\s*\{[^}]*grid-template-columns:\s*192px\s+minmax\(0,\s*1fr\);/s);
  assert.match(styles, /@media\s*\(max-width:\s*620px\)[\s\S]*?\.catalog-row\s*\{[^}]*grid-template-columns:\s*164px\s+minmax\(0,\s*1fr\);/s);
});
