import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../styles.css", import.meta.url), "utf8");

function functionSource(name, nextName) {
  const start = appSource.indexOf(`function ${name}`);
  const end = appSource.indexOf(`function ${nextName}`, start + 1);
  return appSource.slice(start, end);
}

test("video wall renders camera 1 as the main feed and four ordered live thumbnails", () => {
  const renderSource = functionSource("renderVideoWall", "selectCamera");

  assert.match(appSource, /let activeCameraId\s*=\s*cameras\[0\]\.id;/);
  assert.match(renderSource, /class="cam-cell cam-main"/);
  assert.match(renderSource, /id="mainCameraVideo"/);
  assert.match(renderSource, /class="camera-strip"/);
  assert.match(renderSource, /cameras\s*\.map\(/);
  assert.match(renderSource, /class="camera-thumb[^`]*data-camera="\$\{cam\.id\}"/s);
  assert.match(renderSource, /aria-pressed="\$\{isActive\}"/);
  assert.match(renderSource, /class="cam-video camera-thumb-video"/);
});

test("camera selection updates the main feed and exactly one thumbnail state", () => {
  const selectSource = functionSource("selectCamera", "playAllCameras");

  assert.match(selectSource, /cameras\.find\(\(item\)\s*=>\s*item\.id\s*===\s*cameraId\)/);
  assert.match(selectSource, /if\s*\(!camera\)\s*return;/);
  assert.match(selectSource, /activeCameraId\s*=\s*camera\.id;/);
  assert.match(selectSource, /mainVideo\.src\s*=\s*camera\.video;/);
  assert.match(selectSource, /mainVideo\.poster\s*=\s*camera\.poster;/);
  assert.match(selectSource, /thumb\.classList\.toggle\("active",\s*isActive\)/);
  assert.match(selectSource, /thumb\.setAttribute\("aria-pressed",\s*String\(isActive\)\)/);
  assert.match(
    appSource,
    /videoGrid\.addEventListener\("click",[\s\S]*?closest\("\[data-camera\]"\)[\s\S]*?selectCamera\(Number\(button\.dataset\.camera\)\)/
  );
});

test("camera stage occupies the full left panel with a wider workspace allocation", () => {
  assert.match(
    styles,
    /\.video-content\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\);/s
  );
  assert.match(styles,/\.workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1\.15fr\)\s+minmax\(0,\s*1fr\);/s);
  assert.match(styles, /\.video-grid\s*\{[^}]*width:\s*100%;/s);
  assert.match(styles, /\.camera-strip\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\);/s);
  assert.match(styles, /\.camera-thumb\.active\s*\{[^}]*border-color:\s*var\(--cyan\);[^}]*box-shadow:/s);
  assert.match(
    styles,
    /@media\s*\(max-width:\s*900px\)[\s\S]*?\.video-content\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\);/s
  );
});
