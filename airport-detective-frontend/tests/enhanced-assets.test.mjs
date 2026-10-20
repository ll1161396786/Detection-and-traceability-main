import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

const itemAssets = ["0740-v2.png", "0750-v2.png", "0800-v2.png"];
const ownerAssets = [
  "P-01-v2.png",
  "P-02-v2.png",
  "P-03-v2.png",
  "P-04-v2.png",
  "P-06-v2.png",
  "P-07-v2.png",
  "P-09-v2.png",
  "P-10-v2.png",
  "P-13-v2.png"
];

function readPngMetadata(url) {
  const bytes = readFileSync(url);
  assert.deepEqual(
    [...bytes.subarray(0, 8)],
    [137, 80, 78, 71, 13, 10, 26, 10],
    `${url.pathname} should be a PNG`
  );
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    colorType: bytes[25]
  };
}

test("enhanced item assets are fixed-size white-background PNGs", () => {
  for (const filename of itemAssets) {
    const metadata = readPngMetadata(new URL(`../public/media/enhanced/items/${filename}`, import.meta.url));
    assert.equal(metadata.width, 800, filename);
    assert.equal(metadata.height, 500, filename);
    assert.match(appSource, new RegExp(`enhanced/items/${filename.replace(".", "\\.")}`));
  }
});

test("enhanced owner assets are square white-background PNGs and referenced by the UI", () => {
  for (const filename of ownerAssets) {
    const metadata = readPngMetadata(new URL(`../public/media/enhanced/owners/${filename}`, import.meta.url));
    assert.equal(metadata.width, 600, filename);
    assert.equal(metadata.height, 600, filename);
    assert.equal(metadata.colorType, 6, `${filename} should use the expected RGBA encoding`);
    assert.match(appSource, new RegExp(`enhanced/owners/${filename.replace(".", "\\.")}`));
  }
});

test("enhanced images use contain sizing and define original-image fallbacks", () => {
  assert.match(styles, /\.item-thumb\s*\{[^}]*object-fit:\s*contain;[^}]*background:\s*#ffffff;/s);
  assert.match(styles, /\.owner-avatar\s*\{[^}]*object-fit:\s*contain;[^}]*background:\s*#ffffff;/s);
  assert.match(appSource, /data-fallback-src=/);
  assert.match(appSource, /public\/media\/crops\/item\/0740\.jpg/);
  assert.match(appSource, /public\/media\/crops\/owner\/P-01\.jpg/);
});
