import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function setup() {
  const nodes = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {
      hidden: false, events: {}, paused: 0, played: 0,
      pause() { this.paused++; }, load() {}, play: async function() { this.played++; },
      removeAttribute(key) { delete this[key]; },
      addEventListener(event, handler) { this.events[event] = handler; },
    });
    return nodes.get(key);
  };
  const context = vm.createContext({ document: { querySelector: node }, itemList: node('list'),
    activeTrip: { id: 'T-01', no: '接驳车 01' }, AbortController, setTimeout, clearTimeout, console });
  vm.runInContext(readFileSync(new URL('../live-client.js', import.meta.url), 'utf8'), context);
  const run = source => vm.runInContext(source, context);
  context.item = { id:'L001', job_id:'job-one', camera_id:2 };
  return { context, node, run };
}
const result = {url:'/api/clip.mp4',start:.5,end:5.5,duration:5,event_offset:2.5};

test('selected event uses its own job and displays the exact clip timing', async () => {
  const {context,node,run} = setup();
  context.fetch = async (url, options) => {
    assert.equal(url,'/api/jobs/job-one/archive/L001/replay');
    assert.equal(options.method,'POST');
    return {ok:true,json:async()=>result};
  };
  await run('playEventReplay(item)');
  assert.equal(node('#eventReplay').src,result.url);
  assert.equal(node('#eventReplay').played,1);
  assert.match(node('#replayTiming').textContent,/共 5.00 秒/);
});

test('vehicle switch discards a late clip response and releases the old video', async () => {
  const {context,node,run} = setup();
  let complete;
  context.fetch = () => new Promise(resolve => { complete=resolve; });
  const pending = run('playEventReplay(item)');
  run('resetEventReplay(); activeTrip={id:"T-02",no:"接驳车 02"}');
  complete({ok:true,json:async()=>result});
  await pending;
  assert.equal(node('#eventReplay').src,undefined);
  assert.equal(node('#eventReplay').hidden,true);
  assert.equal(node('#replayStatus').textContent,'尚未选择遗留物');
});

test('a failed encode or removed source offers retry without leaving an old clip', async () => {
  const {context,node,run} = setup();
  node('#eventReplay').src='old';
  context.fetch = async()=>({ok:false,json:async()=>({error:'源视频已被替换'})});
  await run('playEventReplay(item)');
  assert.equal(node('#eventReplay').src,undefined);
  assert.equal(node('#replayStatus').textContent,'源视频已被替换');
  assert.equal(node('#replayRetry').hidden,false);
  run('resetEventReplay()');
  assert.equal(node('#replayRetry').hidden,true);
});

test('placement alert takes priority over historical suspected transfers', () => {
  const {run}=setup();
  assert.equal(run('liveAlertLabel({warning_level:"suspected",event_type:"suspected_left_behind",suspected_transfer_count:1,handoff_requires_review:true})'),'疑似行李遗落 · 待复核');
  assert.equal(run('liveAlertLabel({warning_level:"confirmed",event_type:"suspected_left_behind"})'),'遗留红警');
  assert.equal(run('liveAlertLabel({warning_level:"suspected",event_type:"suspected_handoff",handoff_requires_review:true})'),'疑似转交 · 待复核');
});

test('person photo hint distinguishes marked crops from legacy photos', () => {
  const {run}=setup();
  assert.equal(run('liveOwnerPhotoHint({photo:"/api/jobs/a/people/person-P001.jpg?v=2&target=1"})'),'绿框内为关联人');
  for (const photo of ['/old.jpg?v=2','/old.jpg?target=10','']) {
    assert.equal(run(`liveOwnerPhotoHint({photo:${JSON.stringify(photo)}})`),'旧截图未标注，请重新检测');
  }
});

test('person cards retain hidden IDs and show per-photo target instructions', () => {
  const {context,run}=setup();
  context.itemCount={};
  context.itemList.dataset={};
  context.escapeHtml=value=>String(value??'');
  run(`liveState.alerts=[{key:'a',id:'L001',camera_id:1,warning_level:'suspected',owners:[
    {person_id:'P047',probability:.8,photo:'/new.jpg?v=2&target=1',is_recent_owner:true},
    {person_id:'P048',probability:.7,photo:'/old.jpg?v=1'}]}];renderLiveItems()`);
  const html=context.itemList.innerHTML;
  assert.match(html,/最近关联人/);
  assert.match(html,/绿框内为关联人/);
  assert.match(html,/旧截图未标注，请重新检测/);
  assert.doesNotMatch(html,/P047|P048/);
});
