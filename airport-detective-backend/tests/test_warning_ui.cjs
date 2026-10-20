// Validate warning controls and their archive links without a browser dependency.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map();
function element(id){
  if(!elements.has(id))elements.set(id,{id,innerHTML:'',textContent:'',hidden:false,dataset:{},attributes:{},listeners:{},
    classList:{toggle(){},remove(){}},setAttribute(k,v){this.attributes[k]=v},
    addEventListener(k,v){this.listeners[k]=v},querySelectorAll(){return []},querySelector(){return this.innerHTML.includes('archive-row')?{}:null},
    insertAdjacentHTML(position,markup){this.innerHTML+=markup;const match=markup.match(/id="(archive-L\d+)"/);if(match)element(match[1])},
    focus(){this.focused=true},scrollIntoView(){this.scrolled=true}});
  return elements.get(id);
}
const context=vm.createContext({document:{getElementById(id){return id.startsWith('archive-L')?(elements.get(id)||null):element(id)}},window:{addEventListener(){}},
  console,setTimeout,clearTimeout,Map,Set,Intl,Number,String,Math,AbortController});
const source=fs.readFileSync('static/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf('(async()=>{syncTrainLabels();')),context);
vm.runInContext(`
  const fixtureJob={id:'test-job',status:'running',processed:12};
  currentJob=fixtureJob;
  renderArchiveRows([
    {id:'L001',crop:'crop-L001.jpg',label_zh:'背包',warning_level:'suspected',package_photo:'/one.jpg',owners:[]},
    {id:'L002',crop:'crop-L002.jpg',label_zh:'行李箱',warning_level:'confirmed',package_photo:'/two.jpg',owners:[]}
  ],fixtureJob);
`,context);
assert.equal(element('confirmedCount').textContent,1);
assert.equal(element('suspectedCount').textContent,1);
assert.match(element('warningImages').innerHTML,/data-jump-package="L001"/);
assert.match(element('archiveRows').innerHTML,/id="archive-L001"/);
element('suspectedMetric').listeners.click();
assert.equal(element('warningGallery').hidden,false);
assert.equal(element('suspectedMetric').attributes['aria-expanded'],'true');
element('warningImages').listeners.click({target:{closest(selector){return selector==='[data-jump-package]'?{dataset:{jumpPackage:'L001'}}:null}}});
assert.equal(element('archive-L001').focused,true);
assert.equal(element('archive-L001').scrolled,true);
vm.runInContext('resetArchive()',context);
assert.equal(element('confirmedCount').textContent,'0');
assert.equal(element('suspectedCount').textContent,'0');
assert.equal(element('warningGallery').hidden,true);
console.log('Warning counters, gallery controls, archive jump and reset: OK');

(async()=>{
  let finish,requests=0,revoked=0;
  context.fetch=()=>{requests++;return new Promise(resolve=>finish=()=>resolve({ok:true,status:200,blob:async()=>({})}))};
  context.URL={createObjectURL(){return 'blob:test'},revokeObjectURL(){revoked++}};
  context.Image=class {decode(){return Promise.resolve()}};
  element('resultVideo').pause=()=>{};element('sourceVideo').pause=()=>{};
  vm.runInContext("currentJob={id:'preview-job',preview_version:1,status:'running'}",context);
  const first=vm.runInContext('refreshPreview(currentJob)',context);
  await vm.runInContext('refreshPreview(currentJob)',context);
  assert.equal(requests,1,'Only one preview download can be pending');
  finish();await first;
  assert.equal(element('livePreview').src,'blob:test');
  await vm.runInContext('refreshPreview(currentJob)',context);
  assert.equal(requests,1,'Already displayed frame must not reload');
  context.fetch=async()=>{requests++;throw new Error('temporary disconnect')};
  vm.runInContext('currentJob.preview_version=2',context);
  await vm.runInContext('refreshPreview(currentJob)',context);
  assert.equal(element('livePreview').src,'blob:test','Keep last decoded image on failure');
  context.fetch=async()=>{requests++;return {ok:true,status:200,blob:async()=>({})}};
  await vm.runInContext('refreshPreview(currentJob)',context);
  assert.equal(requests,3,'Failed frame can retry and recover');
  vm.runInContext('resetPreview()',context);
  assert.ok(revoked>=1,'Release blob URLs');
  console.log('Preview single-flight, decode, retry and resource cleanup: OK');
})().catch(error=>{console.error(error);process.exitCode=1});
