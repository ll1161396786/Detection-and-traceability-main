import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

test("behavior count follows the behavior title before the risk badge", () => {
  const cardTemplate = appSource.slice(
    appSource.indexOf('<article class="behavior-item"'),
    appSource.indexOf("</article>", appSource.indexOf('<article class="behavior-item"'))
  );

  const titleIndex = cardTemplate.indexOf('class="behavior-title"');
  const countIndex = cardTemplate.indexOf('class="behavior-count"');
  const riskIndex = cardTemplate.indexOf('class="behavior-risk risk-tag');

  assert.ok(titleIndex >= 0, "behavior title should exist");
  assert.ok(countIndex > titleIndex, "count should follow the title");
  assert.ok(riskIndex > countIndex, "risk badge should follow the count");
});

test("behavior evidence images form a left-aligned horizontal row", () => {
  assert.match(
    styles,
    /\.behavior-item\s*\{[^}]*grid-template-columns:\s*minmax\(220px,\s*0\.42fr\)\s+minmax\(0,\s*1fr\)\s+auto;/s
  );
  assert.match(
    styles,
    /\.behavior-shots\s*\{[^}]*display:\s*flex;[^}]*justify-content:\s*flex-start;/s
  );
  assert.match(styles, /\.behavior-shots \.shot\s*\{[^}]*margin:\s*0;/s);
});
