const $ = id => document.getElementById(id);
const terminal = new Set(['completed','cancelled','failed','interrupted']);
const stateNames = {loading:'加载模型',running:'实时分析',exporting:'生成结果',completed:'分析完成',cancelled:'已停止',failed:'分析失败',interrupted:'已中断'};
let ready=false,uploading=false,busy=false,selected=null,currentJob=null,selectedCandidateId=null;
let pollTimer,previewVersion='',mediaKey='',objectUrl=null,toastTimer,playbackPending=false,playbackRequest=0;
let archiveJobId='',archiveSuppressedJobId=null,archiveRequest=0,archiveLoadedKey='',archivePending=false;
let warningFilter=null,focusedPackageId=null;
let previewPending=false,previewController=null,previewBlobUrl=null,previewGeneration=0,archiveReadAt=0;

const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtTime = seconds => {const s=Math.max(0,Math.floor(Number(seconds)||0));return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`};
const fmtNumber = number => Number(number||0).toLocaleString('zh-CN');

function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,7000)}
async function api(url,body){const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);try{const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};const response=await fetch(url,{...options,signal:controller.signal});const payload=await response.json();if(!response.ok)throw new Error(payload.error||'请求失败');return payload}finally{clearTimeout(timeout)}}

function resetPreview(){previewGeneration++;previewController?.abort();previewPending=false;previewVersion='';if(previewBlobUrl){URL.revokeObjectURL(previewBlobUrl);previewBlobUrl=null}}
async function refreshPreview(job){
  const key=`${job.id}:${job.preview_version}`;
  if(previewPending||previewVersion===key||!job.preview_version)return;
  const generation=previewGeneration;previewPending=true;const controller=new AbortController();previewController=controller;
  const timeout=setTimeout(()=>controller.abort(),8000);let url=null;
  try{
    const response=await fetch(`/api/jobs/${job.id}/preview?v=${job.preview_version}`,{signal:controller.signal});
    if(!response.ok||response.status===204)throw new Error('预览暂未生成');
    url=URL.createObjectURL(await response.blob());const decoded=new Image();decoded.src=url;await decoded.decode();
    if(generation!==previewGeneration||currentJob?.id!==job.id||currentJob.archive_cleared||currentJob.status==='completed')return;
    const previous=previewBlobUrl;$('livePreview').src=url;previewBlobUrl=url;url=null;
    if(previous)URL.revokeObjectURL(previous);previewVersion=key;showMedia('livePreview');mediaKey=`${job.id}:live`;
  }catch(error){if(generation===previewGeneration&&currentJob?.id===job.id)$('frameInfo').textContent='预览重试中 · 已保留上一帧'}
  finally{clearTimeout(timeout);if(url)URL.revokeObjectURL(url);if(generation===previewGeneration){previewPending=false;previewController=null}}
}

function trainInfo(){return {number:$('trainNumber').value.trim()||'DT-0421',route:$('trainRoute').value.trim()||'Downtown Line',carriage:$('carriage').value.trim()||'Car 03',camera:$('camera').value.trim()||'CAM-07'}}
function syncTrainLabels(){const train=trainInfo();$('cameraTag').textContent=train.camera;$('trainTag').textContent=`${train.number} · ${train.carriage.toUpperCase()}`}
for(const id of ['trainNumber','trainRoute','carriage','camera'])$(id).addEventListener('input',syncTrainLabels);

function controls(){
  $('start').disabled=!ready||!selected||busy||uploading;
  $('start').innerHTML=uploading?'正在导入视频…':busy?'正在智能研判…':'<span>▶</span> 开始智能研判';
  $('stop').hidden=!currentJob||terminal.has(currentJob.status);
  $('deletePhotos').hidden=!currentJob;
  $('deletePhotos').disabled=!currentJob||!terminal.has(currentJob.status)||!!currentJob.archive_cleared;
  $('deletePhotos').title=busy?'请先停止检测，再删除照片':'';
  for(const id of ['fileInput','library','refreshLibrary','model','device','scope','imgsz','stride','lingerSeconds','confidence','trainNumber','trainRoute','carriage','camera'])$(id).disabled=busy||uploading;
  $('dropzone').classList.toggle('disabled',busy||uploading);
}
function showMedia(id){for(const name of ['empty','sourceVideo','livePreview','resultVideo'])$(name).hidden=name!==id;for(const name of ['sourceVideo','resultVideo'])if(name!==id)$(name).pause();$('hud').hidden=id!=='livePreview'}

function resetAnalysis(){
  resetPreview();
  clearTimeout(pollTimer);currentJob=null;selectedCandidateId=null;previewVersion='';mediaKey='';
  for(const id of ['confirmedCount','suspectedCount','candidateCount','ownerCount'])$(id).textContent='0';
  for(const id of ['processed','currentCount','inferenceFps'])$(id).textContent='—';
  $('overviewProgress').textContent='0%';$('progressText').textContent='0%';$('jobProgress').value=0;$('elapsed').textContent='耗时 —';
  $('statusBadge').textContent=selected?'视频就绪':'等待输入';$('statusBadge').className='analysis-badge';
  $('statusText').textContent=selected?'视频已就绪，点击开始智能研判':'等待选择视频';
  $('alertTitle').textContent='系统待命';$('alertDescription').textContent='导入车厢视频，系统将持续跟踪人员与行李的空间关系。';$('alertBanner').classList.remove('active');
  $('candidateList').innerHTML='<div class="empty-state"><span>⌁</span><h3>尚未发现行李候选</h3><p>模型检测到背包、手提包或行李箱后，将在这里建立跨帧记录。</p></div>';
  $('eventTimeline').innerHTML='<div class="timeline-empty">等待检测事件</div>';$('frameInfo').textContent='检测框来自真实模型输出';
  renderOwners(null);resetArchive();
}
function sourceDescription(meta){return `${meta.name} · ${meta.width}×${meta.height} · ${fmtTime(meta.duration)} · ${Number(meta.fps).toFixed(1)} FPS · ${(meta.size/1024/1024).toFixed(1)} MB`}

async function upload(file){
  if(!file||busy||uploading)return;
  if(!/\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(file.name))return toast('请选择 MP4、MOV、AVI、MKV、WEBM 或 M4V 视频。');
  if(file.size>2*1024**3)return toast('视频超过 2 GB，请放入新版 videos 文件夹后刷新。');
  uploading=true;selected=null;resetAnalysis();controls();showMedia('empty');
  $('uploadTitle').textContent=file.name;$('uploadHint').textContent='正在导入并检查视频';$('uploadProgress').hidden=false;$('uploadBar').value=0;$('library').value='';
  try{
    const meta=await new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/uploads');xhr.responseType='json';xhr.upload.onprogress=e=>{if(e.lengthComputable){const p=Math.round(e.loaded/e.total*100);$('uploadBar').value=p;$('uploadPercent').textContent=p===100?'检查中…':`${p}%`}};xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(xhr.response):reject(new Error(xhr.response?.error||'导入失败'));xhr.onerror=()=>reject(new Error('本地服务连接中断'));const form=new FormData();form.append('video',file);xhr.send(form)});
    selected={upload_id:meta.id};$('fileMeta').textContent=sourceDescription(meta);$('uploadHint').textContent='视频已就绪 · 点击可更换';
    if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(file);$('sourceVideo').src=objectUrl;$('sourceVideo').poster=`/api/uploads/${meta.id}/poster`;showMedia('sourceVideo');
    resetAnalysis();
  }catch(error){toast(error.message);$('fileMeta').textContent='未能导入视频';$('uploadHint').textContent='请重新选择有效视频'}
  finally{uploading=false;$('uploadProgress').hidden=true;$('fileInput').value='';controls()}
}

async function refreshLibrary(){
  try{const data=await api('/api/library');const previous=$('library').value;$('library').innerHTML=`<option value="">${data.files.length?'从 videos 文件夹选择…':'videos 文件夹暂无视频'}</option>`+data.files.map(f=>`<option value="${escapeHtml(f.name)}">${escapeHtml(f.name)} · ${(f.size/1024/1024).toFixed(1)} MB</option>`).join('');if(data.files.some(f=>f.name===previous))$('library').value=previous}
  catch(error){toast(error.message)}
}

function candidatesFor(job){return job.status==='completed'?(job.candidate_summary||job.luggage_candidates||[]):(job.luggage_candidates||[])}
function candidateWarningClass(item){return item.warning_level==='confirmed'?'high':item.warning_level==='suspected'?'medium':item.warning_level==='none'?'low':item.risk||'low'}
function renderCandidates(candidates,job){
  const alerts=candidates.filter(c=>candidateWarningClass(c)==='high').length;const people=new Set(candidates.flatMap(c=>(c.owners||[]).map(o=>o.person_id)));
  $('candidateCount').textContent=candidates.length;$('ownerCount').textContent=people.size;
  if(!candidates.length){const archived=job?.candidate_summary||[];$('candidateList').innerHTML=`<div class="empty-state"><span>⌁</span><h3>${job?.processed?'当前未检出行李候选':'等待视频分析'}</h3><p>持续检测背包、手提包与行李箱，并关联附近人员。</p></div>`;if(!archived.length)selectedCandidateId=null;renderOwners(null,job);renderTimeline([],job);renderArchive(archived,job);return}
  if(!candidates.some(c=>c.id===selectedCandidateId))selectedCandidateId=(candidates.find(c=>candidateWarningClass(c)==='high')||candidates[0]).id;
  $('candidateList').innerHTML=candidates.map(c=>`<button class="candidate ${candidateWarningClass(c)} ${c.id===selectedCandidateId?'selected':''}" data-candidate="${c.id}"><img src="/api/jobs/${job.id}/crops/${c.crop}" alt="${escapeHtml(c.label_zh)} ${c.id}" onerror="this.alt='照片暂不可用'"><span class="candidate-body"><span class="candidate-top"><b class="candidate-name">${c.id} · ${escapeHtml(c.label_zh)}</b><span class="candidate-state">${c.state}</span></span><p>${escapeHtml(c.reason)}</p><span class="candidate-meta"><span>静止 <b>${Number(c.stationary_seconds).toFixed(1)}s</b></span><span>出现 <b>${fmtTime(c.first_seen)}</b></span></span></span></button>`).join('');
  const selectedItem=candidates.find(c=>c.id===selectedCandidateId);renderOwners(selectedItem,job);renderTimeline(candidates,job);renderArchive(job?.candidate_summary||candidates,job);
  $('alertBanner').classList.toggle('active',alerts>0);
  if(alerts){$('alertTitle').textContent=`发现 ${alerts} 个遗留红警，建议人工复核`;$('alertDescription').textContent='包裹连续5帧满足遗留条件，或已经人工确认；请核查证据。'}
  else{$('alertTitle').textContent=candidates.some(c=>c.state==='持续观察')?'行李关系持续分析中':'当前行李均有较强近邻关联';$('alertDescription').textContent='系统正在结合静止时长、空间距离与跨帧共同出现证据更新研判。'}
}

function resetArchive(clearRecords=true,message='等待检测结果'){
  if(clearRecords){resetPreview();archiveRequest++;archiveLoadedKey='';archivePending=false;archiveJobId='';archiveReadAt=0}
  resetWarnings();
  $('archiveCount').textContent='0 条记录';$('archiveStatus').textContent=message;
  $('archiveRows').innerHTML='<div class="archive-empty-row"><span>▣</span><div><b>暂无归档记录</b><small>开始检测后，识别到的包裹会固定保存在此处</small></div></div>';
}

function archiveOwner(owner,job){
  const percent=Math.round(Number(owner.probability||0)*100);
  return `<div class="archive-owner-card">${ownerPhoto(job,owner.person_id)}<div class="archive-owner-info"><span><b>${owner.person_id}</b><strong>${percent}%</strong></span><small>共现 ${fmtNumber(owner.near_frames)} 帧</small><i><em style="width:${percent}%"></em></i></div></div>`;
}

async function renderArchive(candidates,job){
  if(!job)return resetArchive();
  if(archiveJobId!==job.id){resetArchive();archiveJobId=job.id}
  if(job.archive_cleared||archiveSuppressedJobId===job.id){const cleared=!!job.archive_cleared;archiveRequest++;$('archiveCount').textContent='0 条照片记录';$('archiveStatus').textContent=cleared?'存档照片已删除':'正在删除照片';$('archiveRows').innerHTML=cleared?'<div class="archive-empty-row cleared"><span>✓</span><div><b>存档照片已删除</b><small>检测数据与结果视频仍保留在本地</small></div></div>':'<div class="archive-empty-row clearing"><span>◌</span><div><b>正在删除存档照片</b><small>检测数据仍保留</small></div></div>';return}
  const key=`${job.id}:${job.status}:${job.processed||0}`;
  if(archivePending||archiveLoadedKey===key||(!terminal.has(job.status)&&archiveReadAt&&Date.now()-archiveReadAt<2000))return;
  const request=++archiveRequest;archivePending=true;
  try{
    const data=await api(`/api/jobs/${job.id}/archive`);
    if(request!==archiveRequest||currentJob?.id!==job.id||archiveSuppressedJobId===job.id)return;
    archiveLoadedKey=key;
    archiveReadAt=Date.now();
    renderArchiveRows(data.records,job);
  }catch(error){if(request===archiveRequest)$('archiveStatus').textContent=`本地档案读取失败 · ${error.message}`}
  finally{if(request===archiveRequest)archivePending=false}
}

function renderArchiveRows(records,job){
  renderWarningImages(records,job);
  $('archiveCount').textContent=`${records.length} 条记录`;
  $('archiveStatus').textContent=terminal.has(job.status)?'本地归档完成':'持续写入本地';
  if(!records.length){$('archiveRows').innerHTML='<div class="archive-empty-row"><span>▣</span><div><b>暂无归档记录</b><small>识别到包裹后将在此新增固定记录行</small></div></div>';return}
  const rows=records.map((item,index)=>{
    const owners=item.owners||[];
    return `<article id="archive-${item.id}" tabindex="-1" class="archive-row ${candidateWarningClass(item)} ${focusedPackageId===item.id?'archive-highlight':''}" role="row" data-package-id="${item.id}">
      <div class="archive-package-cell" role="cell"><span class="archive-row-number">${String(index+1).padStart(2,'0')}</span><img loading="lazy" decoding="async" src="/api/jobs/${job.id}/crops/${item.crop}" alt="${escapeHtml(item.label_zh)} ${item.id}" onerror="this.alt='照片暂不可用'"><div><b>${item.id} · ${escapeHtml(item.label_zh)}</b><small>${escapeHtml(item.reason||'已建立跨帧包裹记录')}</small></div></div>
      <div class="archive-detection-cell" role="cell"><span>首次检出<b>${fmtTime(item.first_seen)}</b></span><span>最后检出<b>${fmtTime(item.last_seen)}</b></span><span>静止时长<b>${Number(item.stationary_seconds||0).toFixed(1)} 秒</b></span></div>
      <div class="archive-state-cell" role="cell"><span class="archive-risk ${candidateWarningClass(item)}"><i></i>${item.warning_level==='confirmed'?'确认遗留':item.warning_level==='suspected'?'疑似遗留':escapeHtml(item.state||'持续观察')}</span><small>${owners.length} 名关联候选</small></div>
      <div class="archive-owner-cell" role="cell">${owners.length?owners.map(owner=>archiveOwner(owner,job)).join(''):'<div class="archive-owner-empty"><span>?</span><div><b>暂无稳定所属人</b><small>保留包裹记录，继续等待关联</small></div></div>'}</div>
    </article>`;
  });
  const container=$('archiveRows');
  if(!container.querySelector('.archive-row'))container.innerHTML='';
  for(let index=0;index<rows.length;index++){
    const id=`archive-${records[index].id}`,existing=$(id),markup=rows[index];
    if(!existing){container.insertAdjacentHTML('beforeend',markup);$(id).dataset.renderMarkup=markup}
    else if(existing.dataset.renderMarkup!==markup){const template=document.createElement('template');template.innerHTML=markup;const updated=template.content.firstElementChild;
      // Reuse decoded image nodes instead of restarting every photo request.
      const photos=new Map([...existing.querySelectorAll('img')].map(img=>[img.getAttribute('src'),img]));
      for(const img of updated.querySelectorAll('img')){const saved=photos.get(img.getAttribute('src'));if(saved)img.replaceWith(saved)}
      existing.replaceWith(updated);updated.dataset.renderMarkup=markup;
    }
  }
}

function resetWarnings(){
  warningFilter=null;focusedPackageId=null;
  $('confirmedCount').textContent='0';$('suspectedCount').textContent='0';
  $('warningImages').innerHTML='';$('warningImages').dataset.renderMarkup='';$('warningGallery').hidden=true;
  for(const id of ['confirmedMetric','suspectedMetric'])$(id).setAttribute('aria-expanded','false');
}
function showWarnings(level){
  warningFilter=level;$('warningGallery').hidden=!level;
  $('warningGalleryTitle').textContent=level==='confirmed'?'确认遗留 · 图片档案':'疑似遗留 · 图片档案';
  $('warningGallery').classList.toggle('confirmed',level==='confirmed');
  $('confirmedMetric').setAttribute('aria-expanded',String(level==='confirmed'));
  $('suspectedMetric').setAttribute('aria-expanded',String(level==='suspected'));
  for(const group of $('warningImages').querySelectorAll('[data-warning-group]'))group.hidden=group.dataset.warningGroup!==level;
}
function renderWarningImages(records,job){
  const groups={confirmed:records.filter(item=>item.warning_level==='confirmed'),suspected:records.filter(item=>item.warning_level==='suspected')};
  $('confirmedCount').textContent=groups.confirmed.length;$('suspectedCount').textContent=groups.suspected.length;
  const markup=Object.entries(groups).map(([level,items])=>`<div data-warning-group="${level}" ${warningFilter!==level?'hidden':''}>${items.length?items.map(item=>`<article class="warning-card ${level}"><button class="warning-photo" data-jump-package="${item.id}" title="定位 ${item.id} 的证据档案"><img loading="lazy" src="${item.package_photo}" alt="${escapeHtml(item.label_zh)} ${item.id}"><span><b>${item.id} · ${escapeHtml(item.label_zh)}</b><small>查看对应档案 ↓</small></span></button><button class="warning-review" data-confirm-package="${item.id}" data-confirmed="${level!=='confirmed'}">${level==='confirmed'?'撤销确认':'确认遗留'}</button></article>`).join(''):'<p class="warning-empty">暂无对应包裹记录</p>'}</div>`).join('');
  if($('warningImages').dataset.renderMarkup!==markup){$('warningImages').innerHTML=markup;$('warningImages').dataset.renderMarkup=markup}
}
$('confirmedMetric').addEventListener('click',()=>showWarnings(warningFilter==='confirmed'?null:'confirmed'));
$('suspectedMetric').addEventListener('click',()=>showWarnings(warningFilter==='suspected'?null:'suspected'));
$('closeWarnings').addEventListener('click',()=>showWarnings(null));
$('warningImages').addEventListener('click',async event=>{
  const jump=event.target.closest('[data-jump-package]');
  if(jump){focusedPackageId=jump.dataset.jumpPackage;for(const row of $('archiveRows').querySelectorAll('.archive-row'))row.classList.toggle('archive-highlight',row.dataset.packageId===focusedPackageId);const row=$(`archive-${focusedPackageId}`);if(row){row.focus({preventScroll:true});row.scrollIntoView({behavior:'smooth',block:'center'})}return}
  const confirm=event.target.closest('[data-confirm-package]');
  if(!confirm||!currentJob||currentJob.archive_cleared||archiveSuppressedJobId===currentJob.id)return;
  const job=currentJob,id=job.id;confirm.disabled=true;
  // Invalidate any older archive GET so it cannot overwrite the saved review.
  archiveRequest++;archivePending=false;archiveLoadedKey='';
  try{const data=await api(`/api/jobs/${id}/archive/${confirm.dataset.confirmPackage}/confirm`,{confirmed:confirm.dataset.confirmed==='true'});if(currentJob?.id===id&&archiveSuppressedJobId!==id)renderArchiveRows(data.records,currentJob)}catch(error){toast(error.message)}finally{confirm.disabled=false}
});
function ownerPhoto(job,personId){return `<span class="owner-photo-wrap"><span>♙</span><img loading="lazy" decoding="async" src="/api/jobs/${job.id}/people/person-${personId}.jpg" alt="${personId} 人员照片" onerror="this.alt='照片暂不可用'"></span>`}
function renderOwners(item,job){
  if(!item||!job){$('selectedObject').innerHTML='<span>未选择遗留物</span><small>选择中栏候选后查看关联结果</small>';$('ownerHero').className='owner-hero empty-owner';$('ownerHero').innerHTML='<div class="person-silhouette">♙</div><b>等待关联分析</b><p>检测到包裹后，这里会显示可能所属人的存档照片与概率。</p>';$('ownerList').innerHTML='';return}
  $('selectedObject').innerHTML=`<span>${item.id} · ${escapeHtml(item.label_zh)}</span><small>${item.state}</small>`;
  const owners=item.owners||[],best=owners[0];
  if(!best){$('ownerHero').className='owner-hero empty-owner';$('ownerHero').innerHTML='<div class="person-silhouette">?</div><b>暂无稳定所属人</b><p>当前没有人员形成足够的近邻共现证据，请人工回看物品首次出现前后的画面。</p>';$('ownerList').innerHTML='';return}
  const percent=Math.round(best.probability*100);$('ownerHero').className='owner-hero';$('ownerHero').innerHTML=`<div class="owner-primary">${ownerPhoto(job,best.person_id)}<div class="owner-id"><strong>${best.person_id}</strong><span>${best.present?'当前仍在画面':'当前已离开画面'}</span></div><div class="probability" style="--value:${percent}%"><b>${percent}%</b></div></div><p>最高关联候选 · 距离与跨帧共现形成的研判分数</p>`;
  $('ownerList').innerHTML=owners.map(o=>`<div class="owner-row">${ownerPhoto(job,o.person_id)}<span><b>${o.person_id}</b><small>近邻共现 ${o.near_frames} 帧 · ${o.present?'在场':'离场'}</small></span><strong>${Math.round(o.probability*100)}%</strong></div>`).join('');
}
function renderTimeline(candidates,job){
  if(!candidates.length){$('eventTimeline').innerHTML='<div class="timeline-empty">等待检测事件</div>';return}
  const events=[];for(const item of candidates.slice(0,6)){events.push({time:item.first_seen,title:`${item.id} 首次检出`,detail:`${item.label_zh}进入跟踪`});if(item.stationary_seconds>=Number(job?.options?.linger_seconds||3))events.push({time:item.last_seen,title:`${item.id} ${item.state}`,detail:item.owners?.[0]?`关联 ${item.owners[0].person_id} · ${Math.round(item.owners[0].probability*100)}%`:'无稳定所属人',risk:item.risk})}
  events.sort((a,b)=>a.time-b.time);$('eventTimeline').innerHTML=events.slice(-7).map(e=>`<div class="timeline-item ${e.risk||''}"><b>${fmtTime(e.time)} · ${escapeHtml(e.title)}</b><span>${escapeHtml(e.detail)}</span></div>`).join('');
}

function renderJob(job){
  currentJob=job;busy=!terminal.has(job.status);controls();
  if(job.train){$('trainNumber').value=job.train.number;$('trainRoute').value=job.train.route;$('carriage').value=job.train.carriage;$('camera').value=job.train.camera;syncTrainLabels()}
  $('statusBadge').textContent=stateNames[job.status]||job.status;$('statusBadge').className=`analysis-badge ${job.status}`;$('statusText').textContent=job.message;
  const progress=Math.round(job.progress||0);$('progressText').textContent=`${progress}%`;$('overviewProgress').textContent=`${progress}%`;$('jobProgress').value=progress;
  $('processed').textContent=fmtNumber(job.processed);$('currentCount').textContent=fmtNumber(job.current_count);$('inferenceFps').textContent=job.inference_fps||'—';$('elapsed').textContent=`耗时 ${fmtTime(job.elapsed)}`;$('videoTime').textContent=`${fmtTime(job.time)} / ${fmtTime(job.source.duration)}`;
  $('frameInfo').textContent=`第 ${fmtNumber(job.frame)} 帧 · ${job.options.model.replace('.pt','')} · ${job.device||'加载中'}`;
  renderCandidates(candidatesFor(job),job);
  if(job.status==='completed'){
    if(mediaKey!==`${job.id}:result`){$('resultVideo').src=`/api/jobs/${job.id}/files/result.mp4`;showMedia('resultVideo');mediaKey=`${job.id}:result`}
  }else{
    if(job.preview_version)refreshPreview(job);else showMedia('empty');
  }
  $('stop').disabled=!!job.cancel;$('stop').textContent=job.cancel?'正在停止…':'■ 停止检测';
}

async function poll(){if(!currentJob)return;const id=currentJob.id;try{const job=await api(`/api/jobs/${id}`);if(currentJob?.id!==id)return;renderJob(job);if(terminal.has(job.status))return}catch(error){$('statusText').textContent=`连接中断，正在重试 · ${error.message}`}pollTimer=setTimeout(poll,650)}
async function selectJob(id){if(uploading||(busy&&currentJob?.id!==id))return;clearTimeout(pollTimer);const job=await api(`/api/jobs/${id}`);selected=job.source.id?{upload_id:job.source.id}:{library_name:job.source.name};$('fileMeta').textContent=sourceDescription(job.source);$('uploadTitle').textContent=job.source.name;$('uploadHint').textContent='当前任务视频';for(const key of ['model','device','scope','imgsz','stride','confidence'])if(job.options[key]!==undefined)$(key).value=job.options[key];$('lingerSeconds').value=String(job.options.linger_seconds||3);$('confidenceValue').textContent=Number(job.options.confidence).toFixed(2);previewVersion='';mediaKey='';renderJob(job);if(!terminal.has(job.status))pollTimer=setTimeout(poll,500)}
async function restoreCurrentJob(){try{const data=await api('/api/jobs?latest=1');const current=data.jobs.find(j=>!terminal.has(j.status))||data.jobs.find(j=>j.status==='completed'&&!j.archive_cleared)||data.jobs[0];if(current)await selectJob(current.id)}catch(error){toast(error.message)}}

async function syncPlayback(){if(currentJob?.status!=='completed'||$('resultVideo').hidden||playbackPending)return;const job=currentJob,seconds=$('resultVideo').currentTime;if(seconds<.05&&$('resultVideo').paused)return;const version=++playbackRequest;playbackPending=true;try{const frame=await api(`/api/jobs/${job.id}/frame?time=${seconds}`);if(currentJob?.id!==job.id||version!==playbackRequest)return;renderCandidates(frame.luggage_candidates||[],job);$('currentCount').textContent=frame.boxes.length;$('frameInfo').textContent=`回放 ${fmtTime(seconds)} · 原视频第 ${fmtNumber(frame.frame)} 帧 · ${job.options.model.replace('.pt','')}`}catch(error){if(currentJob?.id===job.id)$('frameInfo').textContent=error.message}finally{playbackPending=false;if(currentJob?.id===job.id&&Math.abs($('resultVideo').currentTime-seconds)>.08)syncPlayback()}}
for(const event of ['loadeddata','timeupdate','seeked'])$('resultVideo').addEventListener(event,syncPlayback);

$('candidateList').addEventListener('click',event=>{const button=event.target.closest('[data-candidate]');if(!button||!currentJob)return;selectedCandidateId=button.dataset.candidate;renderCandidates(candidatesFor(currentJob),currentJob)});
$('fileInput').addEventListener('change',event=>upload(event.target.files[0]));$('dropzone').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&!busy&&!uploading){event.preventDefault();$('fileInput').click()}});
for(const event of ['dragenter','dragover'])$('dropzone').addEventListener(event,e=>{e.preventDefault();if(!busy&&!uploading)$('dropzone').classList.add('dragover')});for(const event of ['dragleave','drop'])$('dropzone').addEventListener(event,e=>{e.preventDefault();$('dropzone').classList.remove('dragover')});$('dropzone').addEventListener('drop',e=>upload(e.dataTransfer.files[0]));window.addEventListener('dragover',e=>e.preventDefault());window.addEventListener('drop',e=>e.preventDefault());
$('refreshLibrary').addEventListener('click',refreshLibrary);$('library').addEventListener('change',()=>{const name=$('library').value;selected=name?{library_name:name}:null;resetAnalysis();if(name){$('fileMeta').textContent=`已选择 ${name}`;$('sourceVideo').src=`/api/library/media/${encodeURIComponent(name)}`;showMedia('sourceVideo')}else showMedia('empty');controls()});
$('confidence').addEventListener('input',event=>$('confidenceValue').textContent=Number(event.target.value).toFixed(2));
$('start').addEventListener('click',async()=>{if(!selected||busy||uploading)return;busy=true;archiveSuppressedJobId=null;resetArchive();controls();try{const body={...selected,train:trainInfo(),linger_seconds:$('lingerSeconds').value};for(const key of ['model','device','scope','confidence','imgsz','stride'])body[key]=$(key).value;const job=await api('/api/jobs',body);currentJob=job;selectedCandidateId=null;previewVersion='';mediaKey='';$('fileMeta').textContent=sourceDescription(job.source);renderJob(job);clearTimeout(pollTimer);pollTimer=setTimeout(poll,450)}catch(error){busy=false;controls();toast(error.message);$('statusText').textContent=error.message}});
$('stop').addEventListener('click',async()=>{if(!currentJob||!busy)return;const id=currentJob.id;$('stop').disabled=true;try{const job=await api(`/api/jobs/${id}/cancel`,{});if(currentJob?.id===id)renderJob(job)}catch(error){toast(error.message);$('stop').disabled=false}});
$('deletePhotos').addEventListener('click',async()=>{if(!currentJob||!terminal.has(currentJob.status)||currentJob.archive_cleared)return;const id=currentJob.id;$('deletePhotos').disabled=true;archiveSuppressedJobId=id;resetArchive();archiveJobId=id;try{const job=await api(`/api/jobs/${id}/archive/clear`,{});if(currentJob?.id===id){renderJob(job);toast('存档照片已删除，检测数据仍保留')}}catch(error){archiveSuppressedJobId=null;archiveLoadedKey='';archivePending=false;renderArchive([],currentJob);controls();toast(error.message)}});
$('sourceVideo').addEventListener('error',()=>{$('statusText').textContent='浏览器无法预览该编码，仍可交给本地引擎识别。'});$('livePreview').addEventListener('error',()=>previewVersion='');window.addEventListener('beforeunload',()=>{if(objectUrl)URL.revokeObjectURL(objectUrl)});

async function health(){try{const data=await api('/api/health');ready=data.ready&&data.models.length>0;$('connection').textContent=ready?'本地引擎就绪':'缺少模型文件';$('connectionDot').classList.toggle('online',ready);$('deviceName').textContent=data.hardware.device;$('gpuOption').disabled=!data.hardware.cuda;if($('model').options.length<2)$('model').innerHTML=data.models.map(m=>`<option value="${m.name}">${m.name.replace('.pt','').replace('yolo','YOLO')} · ${m.size_mb} MB</option>`).join('')}catch{$('connection').textContent='本地引擎未连接';$('connectionDot').classList.remove('online');ready=false}controls()}
function tickClock(){$('clock').textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Singapore',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date())}
(async()=>{syncTrainLabels();tickClock();setInterval(tickClock,1000);await health();await Promise.all([refreshLibrary(),restoreCurrentJob()]);setInterval(health,15000)})();
