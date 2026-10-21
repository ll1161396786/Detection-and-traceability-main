let liveState = { cameras: [], alerts: [], status: "idle" };
const liveStates = new Map();
let liveConnectionError = "";
let liveSelectedKey = null;
const livePictures = new Map();
const livePreviewRequests = new Map();
let livePollBusy = false;
let liveControlBusy = false;
let liveClearBusy = false;
let liveModelInitialized = false;

function isLiveTrip(trip) { return /^T-[0-9]{2}$/.test(trip.id); }
function monitorPath(action, trip = activeTrip) {
  return `/api/shuttles/${trip.id.slice(2)}/${action}`;
}
function resetLivePictures() {
  for (const controller of livePreviewRequests.values()) controller.abort();
  livePreviewRequests.clear();
  for (const picture of livePictures.values()) URL.revokeObjectURL(picture.url);
  livePictures.clear();
}
function activateLiveTrip() {
  resetLivePictures();
  liveState = liveStates.get(activeTrip.id) || { trip_id: activeTrip.id, cameras: [], alerts: [], status: "idle" };
  liveSelectedKey = null;
  liveItemsSignature = "";
  liveModelInitialized = false;
}

function updateHeaderControls() {
  const clear = document.querySelector("#clearCacheButton");
  const model = document.querySelector("#modelSelector");
  if (model) {
    model.disabled = liveControlBusy || liveClearBusy || liveState.status === "running" || liveState.cameras.some(c => ["loading", "running"].includes(c.status));
    model.title = model.disabled ? "请先点击左下角停止检测，再切换模型" : "选择模型后，点击左下角启动检测生效";
  }
  if (clear) {
    clear.disabled = liveControlBusy || liveClearBusy;
    clear.textContent = liveClearBusy ? "清理中…" : "清除缓存";
  }
}

async function monitorApi(path, body) {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "后端请求失败");
  return result;
}

function liveTripVerdict(trip = activeTrip) {
  const state = liveStates.get(trip.id) || { cameras: [], alerts: [], status: "idle" };
  if (liveConnectionError) return { label: "连接中断", className: "danger" };
  if (state.alerts.some(a => a.warning_level === "confirmed")) return { label: "确认遗留", className: "danger" };
  if (state.alerts.length) return { label: "疑似遗留", className: "suspected" };
  return { label: state.status === "running" ? "检测中" : state.ready ? "待检测" : "待配置", className: "" };
}

function liveTripClip(trip = activeTrip) {
  const item = liveStates.get(trip.id)?.alerts[0];
  if (!item) return null;
  return { object: { id: item.id, preview: item.package_photo, previewFallback: "",
    risk: item.warning_level === "confirmed" ? "高" : "中" } };
}

function renderLiveVideoWall() {
  videoGrid.innerHTML = `<figure class="cam-cell cam-main" data-cam="${activeCameraId}">
    <img class="cam-video live-frame" id="mainCameraPrediction" alt="等待模型预测画面" hidden />
    <div class="live-frame-message" id="liveFrameMessage">正在连接后端模型…</div>
    <div class="cam-shade"></div><span class="cam-live" id="liveMainStatus">等待模型</span>
    <span class="cam-badge" id="mainCameraBadge">摄像头 ${activeCameraId}</span>
  </figure><div class="camera-strip" role="group" aria-label="四路模型预测画面">${[1, 2, 3, 4].map(id => `
    <button class="camera-thumb ${id === activeCameraId ? "active" : ""}" type="button" data-camera="${id}" aria-pressed="${id === activeCameraId}">
      <img class="cam-video camera-thumb-video live-frame" data-prediction="${id}" alt="摄像头 ${id} 等待模型" hidden />
      <span class="camera-thumb-shade"></span><span class="camera-thumb-live" data-live-status="${id}">等待模型</span>
      <span class="camera-thumb-label">摄像头 ${id}</span>
    </button>`).join("")}</div>
    <div class="live-controls"><button type="button" data-monitor="start">启动四路检测</button>
      <button type="button" data-monitor="stop">停止检测</button><span id="liveMonitorMessage"></span></div>`;
  updateLivePictures();
  updateLiveStatus();
}

function selectLiveCamera(id) {
  if (![1, 2, 3, 4].includes(id)) return;
  activeCameraId = id;
  videoGrid.querySelectorAll(".camera-thumb").forEach(el => {
    el.classList.toggle("active", Number(el.dataset.camera) === id);
    el.setAttribute("aria-pressed", String(Number(el.dataset.camera) === id));
  });
  videoGrid.querySelector(".cam-main").dataset.cam = String(id);
  videoGrid.querySelector("#mainCameraBadge").textContent = `摄像头 ${id}`;
  const main = videoGrid.querySelector("#mainCameraPrediction");
  main.hidden = true;
  main.removeAttribute("src");
  updateLivePictures();
  updateLiveStatus();
}

function updateLivePictures() {
  if (!isLiveTrip(activeTrip)) return;
  livePictures.forEach((picture, id) => {
    const thumb = videoGrid.querySelector(`[data-prediction="${id}"]`);
    if (thumb && thumb.getAttribute("src") !== picture.url) { thumb.src = picture.url; thumb.hidden = false; thumb.alt = `摄像头 ${id} YOLOv10 实时预测结果`; }
    if (id === activeCameraId) {
      const main = videoGrid.querySelector("#mainCameraPrediction");
      if (main && main.getAttribute("src") !== picture.url) main.src = picture.url;
      if (main) { main.hidden = false; main.alt = `摄像头 ${id} YOLOv10 实时预测结果`; }
    }
  });
}

function updateLiveStatus() {
  updateHeaderControls();
  if (!isLiveTrip(activeTrip)) return;
  const online = liveState.cameras.filter(c => c.status === "running" && c.preview_version > 0).length;
  wallStatus.textContent = liveConnectionError ? "后端连接中断" : `${online}/4 模型运行中`;
  liveState.cameras.forEach(c => {
    const thumb = videoGrid.querySelector(`[data-camera="${c.id}"]`);
    if (thumb) thumb.title = `摄像头 ${c.id} · ${c.source}`;
    const label = videoGrid.querySelector(`[data-live-status="${c.id}"]`);
    if (label) label.textContent = liveConnectionError ? "连接中断" : c.status === "running" ? `预测 ${c.fps} fps` : c.status === "loading" ? "加载模型" : c.status === "failed" ? "检测失败" : "已停止";
  });
  const camera = liveState.cameras.find(c => c.id === activeCameraId);
  const label = videoGrid.querySelector("#liveMainStatus");
  if (label) label.textContent = liveConnectionError ? "连接中断 · 上次预测" : camera?.status === "running" ? `模型预测 · ${camera.video_time.toFixed(1)}s · 第 ${camera.cycle} 轮` : camera?.message || "等待模型";
  const frameMessage = videoGrid.querySelector("#liveFrameMessage");
  if (frameMessage) {
    frameMessage.hidden = livePictures.has(activeCameraId);
    frameMessage.textContent = liveConnectionError || (!liveState.cameras.length && liveState.configuration_error) || camera?.message || "点击启动四路检测";
  }
  const message = videoGrid.querySelector("#liveMonitorMessage");
  if (message) message.textContent = liveConnectionError || (!liveState.cameras.length && liveState.configuration_error) || (liveState.status === "running" ? "" : liveState.cameras.length ? "检测已停止 · 保留警报档案" : "放入四个视频后启动检测");
  videoGrid.querySelectorAll("[data-monitor]").forEach(button => {
    button.disabled = liveControlBusy || liveClearBusy || (button.dataset.monitor === "start" ? liveState.status === "running" || liveState.cameras.some(c => ["loading", "running"].includes(c.status)) : liveState.status !== "running");
  });
}

let liveItemsSignature = "";
function renderLiveItems() {
  const confirmed = liveState.alerts.filter(a => a.warning_level === "confirmed").length;
  itemCount.textContent = `确认 ${confirmed} · 疑似 ${liveState.alerts.length - confirmed}`;
  const signature = JSON.stringify([liveState.alerts, liveSelectedKey, liveConnectionError]);
  if (signature === liveItemsSignature && itemList.dataset.live === "true") return;
  liveItemsSignature = signature;
  itemList.dataset.live = "true";
  itemList.innerHTML = liveState.alerts.length ? liveState.alerts.map(item => {
    const isConfirmed = item.warning_level === "confirmed";
    const level = isConfirmed ? "danger" : "suspected";
    return `<article class="item-row ${level} ${item.key === liveSelectedKey ? "active" : ""}" data-live-key="${escapeHtml(item.key)}">
      <div class="item-identity"><img class="item-thumb" src="${item.package_photo}" alt="${item.id} 遗留物截图" loading="lazy" tabindex="0" role="button" aria-haspopup="dialog" title="点击放大照片" />
        <div class="item-meta"><div class="item-title"><strong>CAM-${item.camera_id} · ${item.id}</strong>
          <span class="row-flag ${level}">${isConfirmed ? "确认遗留" : "疑似遗留"}</span></div>
          <p class="item-name">${escapeHtml(item.label_zh)}</p>
          <span class="row-sub">${escapeHtml(activeTrip.no)} · 静止 ${item.stationary_seconds}s</span>
          <p class="live-reason" title="${escapeHtml(item.reason)}">${escapeHtml(item.reason)}</p>
          <button class="live-confirm" type="button" data-confirm-job="${item.job_id}" data-confirm-item="${item.id}" data-confirmed="${!isConfirmed}">${isConfirmed ? "撤销确认" : "确认遗留"}</button>
        </div></div>
      <div class="owner-list">${item.owners.length ? item.owners.slice(0, 3).map(owner => `
        <div class="owner-card" title="所属人关联分数，需人工复核"><img class="owner-avatar" src="${owner.photo}" alt="CAM-${item.camera_id} ${owner.person_id} 可能所属人截图" loading="lazy" tabindex="0" role="button" aria-haspopup="dialog" title="点击放大照片" />
          <div class="owner-body"><div class="owner-top"><strong>${owner.person_id}</strong><span class="owner-score">${Math.round(owner.probability * 100)}%</span></div><span class="owner-name">可能所属人 · 关联分数</span></div></div>`).join("") : '<span class="live-empty-owner">暂无所属人关联证据</span>'}</div>
    </article>`;
  }).join("") : `<p class="live-empty">${liveConnectionError ? "后端连接中断，等待恢复" : "暂无遗留物警报"}</p>`;
}

async function loadLivePreview(camera) {
  const tripId = activeTrip.id;
  if (liveClearBusy || camera.archive_cleared || !camera.preview_version || livePreviewRequests.has(camera.id)) return;
  const version = `${camera.job_id}:${camera.preview_version}`;
  if (livePictures.get(camera.id)?.version === version) return;
  const controller = new AbortController();
  livePreviewRequests.set(camera.id, controller);
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(`${camera.preview}?v=${camera.preview_version}`, { signal: controller.signal });
    if (!response.ok || response.status === 204) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    try {
      const decoded = new Image();
      decoded.src = url;
      await decoded.decode();
      if (tripId !== activeTrip.id || controller.signal.aborted || liveClearBusy || !liveState.cameras.some(c => c.id === camera.id && c.job_id === camera.job_id && !c.archive_cleared)) { URL.revokeObjectURL(url); return; }
      const old = livePictures.get(camera.id);
      livePictures.set(camera.id, { url, version });
      updateLivePictures();
      updateLiveStatus();
      if (old) URL.revokeObjectURL(old.url);
    } catch (error) { URL.revokeObjectURL(url); throw error; }
  } catch (error) {
    // Keep the last fully decoded prediction and retry on the next state poll.
    console.debug("Prediction preview retry", camera.id, error.message);
  } finally {
    clearTimeout(timeout);
    if (livePreviewRequests.get(camera.id) === controller) livePreviewRequests.delete(camera.id);
  }
}

async function pollLiveState() {
  if (livePollBusy || liveClearBusy || liveControlBusy) return;
  livePollBusy = true;
  try {
    const fleet = await monitorApi("/api/shuttles");
    for (const state of fleet.shuttles) {
      liveStates.set(state.trip_id, state);
      if (!trips.some(trip => trip.id === state.trip_id)) {
        const number = state.shuttle_id;
        trips.push({ id: state.trip_id, no: `接驳车 ${number}`, full: `樟宜机场接驳车 ${number}`,
          depart: "—", flight: "—", route: "本地四路视频", status: "待检测", statusClass: "", clipId: null });
      }
    }
    liveState = liveStates.get(activeTrip.id) || { trip_id: activeTrip.id, cameras: [], alerts: [], status: "idle" };
    if (!liveModelInitialized) {
      const model = document.querySelector("#modelSelector");
      if (model && liveState.model) model.value = liveState.model;
      liveModelInitialized = true;
    }
    liveConnectionError = "";
    // Independent requests are bounded to one in-flight preview per camera.
    for (const camera of liveState.cameras) void loadLivePreview(camera);
  } catch (error) { liveConnectionError = error.message; }
  finally {
    livePollBusy = false;
    updateHeaderControls();
    if (isLiveTrip(activeTrip)) { updateLiveStatus(); renderLiveItems(); }
    renderTrips();
  }
}

async function controlLiveMonitor(action) {
  if (liveControlBusy || liveClearBusy) return;
  liveControlBusy = true;
  updateLiveStatus();
  try {
    while (livePollBusy) await new Promise(resolve => setTimeout(resolve, 50));
    const options = action === "start" ? { model: document.querySelector("#modelSelector").value } : {};
    liveState = await monitorApi(monitorPath(action), options);
    liveStates.set(activeTrip.id, liveState);
    liveConnectionError = "";
    if (action === "start") {
      resetLivePictures();
      renderLiveVideoWall();
    }
  } catch (error) { liveConnectionError = error.message; showToast(error.message); }
  finally { liveControlBusy = false; await pollLiveState(); }
}

async function clearLiveCache() {
  if (liveClearBusy || liveControlBusy) return;
  liveClearBusy = true;
  updateLiveStatus();
  let cleared = 0;
  try {
    // Wait for an older state fetch to finish so it cannot restore deleted rows.
    while (livePollBusy) await new Promise(resolve => setTimeout(resolve, 50));
    liveState = await monitorApi(monitorPath("stop"), {});
    const deadline = Date.now() + 45000;
    while (liveState.cameras.some(c => !["completed", "cancelled", "failed", "interrupted"].includes(c.status))) {
      if (Date.now() >= deadline) throw new Error("检测尚未停止，未删除照片；请稍后再次清理。");
      await new Promise(resolve => setTimeout(resolve, 300));
      liveState = await monitorApi(monitorPath("state"));
    }
    for (const camera of liveState.cameras) {
      await monitorApi(`/api/jobs/${camera.job_id}/archive/clear`, {});
      camera.archive_cleared = true;
      cleared += 1;
    }
    liveState = await monitorApi(monitorPath("state"));
    liveStates.set(activeTrip.id, liveState);
    liveConnectionError = "";
    liveSelectedKey = null;
    showToast(cleared ? "已停止四路检测并删除存档照片；点击开始检测可重新运行。" : "当前没有需要清理的四路任务。");
  } catch (error) {
    showToast(cleared ? `已清理 ${cleared} 路，剩余清理失败：${error.message}` : error.message);
  } finally {
    for (const request of livePreviewRequests.values()) request.abort();
    for (const picture of livePictures.values()) URL.revokeObjectURL(picture.url);
    livePictures.clear();
    liveClearBusy = false;
    liveItemsSignature = "";
    if (isLiveTrip(activeTrip)) renderLiveVideoWall();
    updateHeaderControls();
    await pollLiveState();
  }
}

async function initializeLiveMonitor() {
  initializeItemPhotoPreview();
  document.querySelector("#clearCacheButton").addEventListener("click", () => { void clearLiveCache(); });
  videoGrid.addEventListener("click", event => {
    const button = event.target.closest("[data-monitor]");
    if (button) void controlLiveMonitor(button.dataset.monitor);
  });
  itemList.addEventListener("click", async event => {
    const confirm = event.target.closest("[data-confirm-job]");
    if (confirm) {
      confirm.disabled = true;
      try {
        await monitorApi(`/api/jobs/${confirm.dataset.confirmJob}/archive/${confirm.dataset.confirmItem}/confirm`, { confirmed: confirm.dataset.confirmed === "true" });
        await pollLiveState();
      } catch (error) { showToast(error.message); }
      finally { confirm.disabled = false; }
      return;
    }
    const row = event.target.closest("[data-live-key]");
    if (row) {
      liveSelectedKey = row.dataset.liveKey;
      const item = liveState.alerts.find(a => a.key === liveSelectedKey);
      if (item) selectLiveCamera(item.camera_id);
      renderLiveItems();
    }
  });
  await pollLiveState();
  // Input folders may be empty on a new installation; start explicitly after configuration.
  setInterval(() => { void pollLiveState(); }, 600);
}

function initializeItemPhotoPreview() {
  const dialog = document.createElement("dialog");
  dialog.className = "item-photo-dialog";
  dialog.setAttribute("aria-labelledby", "itemPhotoPreviewTitle");
  dialog.innerHTML = `<div class="item-photo-heading"><strong id="itemPhotoPreviewTitle">遗留物照片</strong><button type="button" aria-label="关闭照片预览" autofocus>关闭 ×</button></div>
    <div class="item-photo-content"><img alt="" hidden /><p role="status">正在加载照片…</p></div>`;
  document.body.append(dialog);
  const picture = dialog.querySelector("img");
  const status = dialog.querySelector("[role=status]");
  let returnFocus = null;
  picture.addEventListener("load", () => { picture.hidden = false; status.hidden = true; });
  picture.addEventListener("error", () => { picture.hidden = true; status.hidden = false; status.textContent = "照片暂时无法加载，可能已被清理。"; });
  dialog.querySelector("button").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
  dialog.addEventListener("close", () => {
    picture.removeAttribute("src");
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    else document.querySelector("#clearCacheButton")?.focus({ preventScroll: true });
  });
  const openPhoto = (event, image) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    returnFocus = image;
    picture.hidden = true;
    status.hidden = false;
    status.textContent = "正在加载照片…";
    picture.alt = image.alt || "遗留物照片";
    dialog.querySelector("strong").textContent = picture.alt;
    picture.src = image.currentSrc || image.src;
    dialog.showModal();
  };
  // Capture before the existing row-selection handlers, including dynamically refreshed rows.
  itemList.addEventListener("click", event => {
    const image = event.target.closest("img.item-thumb, img.owner-avatar");
    if (image) openPhoto(event, image);
  }, true);
  itemList.addEventListener("keydown", event => {
    if ((event.key === "Enter" || event.key === " ") && event.target.matches("img.item-thumb, img.owner-avatar")) openPhoto(event, event.target);
  }, true);
}
