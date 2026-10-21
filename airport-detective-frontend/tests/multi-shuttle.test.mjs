import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function setup() {
  const nodes = new Map();
  const revoked = [];
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {
      value: 'yolov10n.pt', dataset: {}, classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {}, querySelector: node, querySelectorAll: () => [],
      setAttribute() {}, removeAttribute() {}, style: { setProperty() {} },
      getBoundingClientRect: () => ({ width: 100, height: 100 }),
    });
    return nodes.get(key);
  };
  const context = vm.createContext({
    document: { querySelector: node, addEventListener() {} },
    window: { clearTimeout, setTimeout, addEventListener() {} },
    setTimeout, clearTimeout, AbortSignal, AbortController, console,
    requestAnimationFrame() {},
    URL: { createObjectURL: () => 'blob:old-vehicle', revokeObjectURL: value => revoked.push(value) },
  });
  const live = readFileSync(new URL('../live-client.js', import.meta.url), 'utf8');
  const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
  vm.runInContext(live + '\n' + app.slice(0, app.lastIndexOf('\nrenderVideoWall();')), context);
  vm.runInContext(`globalThis.realRenderTrips = renderTrips; renderTrips = () => {}; renderCurrentTrip = () => {};
    renderLiveVideoWall = () => {}; renderLiveItems = () => {};
    updateHeaderControls = () => {}; updateLiveStatus = () => {}; showToast = () => {};`, context);
  return { context, revoked, run: text => vm.runInContext(text, context) };
}
const state = (number, overrides = {}) => ({ trip_id: `T-${number}`, shuttle_id: number,
  cameras: [], alerts: [], status: 'idle', model: 'yolov10n.pt', ready: true, ...overrides });
const response = data => ({ ok: true, json: async () => data });

test('default selection is 01 and the fleet list sorts existing and discovered numbers', () => {
  const { run } = setup();
  assert.equal(run('activeTrip.id'), 'T-01');
  run('trips.push({ ...trips[0], id: "T-10" }, { ...trips[0], id: "T-09" }); realRenderTrips()');
  const markup = run('tripList.innerHTML');
  const numbers = [...markup.matchAll(/data-trip="T-([0-9]+)"/g)].map(match => Number(match[1]));
  assert.deepEqual(numbers, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
});

test('vehicles without old demo clips can select and start their own backend', async () => {
  const { context, run } = setup();
  const calls = [];
  context.fetch = async (path, options) => {
    calls.push([path, options]);
    return response(path === '/api/shuttles' ? { shuttles: [state('02')] } : state('02'));
  };
  run('selectTrip("T-02")');
  assert.equal(run('activeTrip.id'), 'T-02');
  await run('controlLiveMonitor("start")');
  assert.equal(calls[0][0], '/api/shuttles/02/start');
  assert.equal(JSON.parse(calls[0][1].body).model, 'yolov10n.pt');
});

test('a state response arriving after a vehicle switch uses the new selection', async () => {
  const { context, run } = setup();
  let finish;
  context.fetch = () => new Promise(resolve => { finish = resolve; });
  const poll = run('pollLiveState()');
  run('selectTrip("T-03")');
  finish(response({ shuttles: [state('02', { alerts: [{ key: '02-only' }] }), state('03')] }));
  await poll;
  assert.equal(run('liveState.trip_id'), 'T-03');
  assert.equal(run('liveState.alerts.length'), 0);
});

test('late image decode cannot show the old vehicle or remove a new request', async () => {
  const { context, run, revoked } = setup();
  let decoded;
  context.Image = class { decode() { return new Promise(resolve => { decoded = resolve; }); } };
  context.fetch = async () => ({ ok: true, status: 200, blob: async () => ({}) });
  context.initial = state('02', { cameras: [{ id: 1, job_id: 'old-job', preview_version: 1, preview: '/old' }] });
  run('liveStates.set("T-02", initial); selectTrip("T-02")');
  const pending = run('loadLivePreview(liveState.cameras[0])');
  await new Promise(resolve => setImmediate(resolve));
  run('selectTrip("T-03"); globalThis.newRequest = new AbortController(); livePreviewRequests.set(1, newRequest)');
  decoded();
  await pending;
  assert.equal(run('livePictures.size'), 0);
  assert.ok(run('livePreviewRequests.get(1) === newRequest'));
  assert.deepEqual(revoked, ['blob:old-vehicle']);
});

test('clear cache only targets the selected vehicle jobs', async () => {
  const { context, run } = setup();
  const selected = state('02', { cameras: [{ id: 1, job_id: '02-job', status: 'cancelled' }] });
  const calls = [];
  context.fetch = async path => {
    calls.push(path);
    return response(path === '/api/shuttles' ? { shuttles: [selected, state('03')] } : selected);
  };
  context.selected = selected;
  run('liveStates.set("T-02", selected); selectTrip("T-02")');
  await run('clearLiveCache()');
  assert.ok(calls.includes('/api/jobs/02-job/archive/clear'));
  assert.ok(calls.includes('/api/shuttles/02/stop'));
  assert.ok(!calls.some(path => path.includes('/03/') || path.includes('/04/')));
});
