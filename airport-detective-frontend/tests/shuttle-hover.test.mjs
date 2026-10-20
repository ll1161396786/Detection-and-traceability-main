import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

test("shuttle views are ordered front, side, rear inside the blue shuttle trigger", () => {
  const triggerStart = html.indexOf('class="train-preview"');
  const triggerEnd = html.indexOf('<span class="train-meta"', triggerStart);
  const previewMarkup = html.slice(triggerStart, triggerEnd);

  assert.ok(triggerStart >= 0, "the blue shuttle label should own the preview");
  assert.ok(previewMarkup.indexOf("front.jpg") >= 0, "front view should exist");
  assert.ok(previewMarkup.indexOf("side.jpg") > previewMarkup.indexOf("front.jpg"));
  assert.ok(previewMarkup.indexOf("rear.jpg") > previewMarkup.indexOf("side.jpg"));
});

test("shuttle views stay hidden until the blue shuttle label is hovered", () => {
  assert.match(styles, /\.view-stack\s*\{[^}]*display:\s*none;/s);
  assert.match(
    styles,
    /\.train-preview:hover\s+\.view-stack\s*\{[^}]*display:\s*grid;/s
  );
  assert.match(styles, /\.view-stack\s*\{[^}]*grid-template-columns:\s*repeat\(3,/s);
});
