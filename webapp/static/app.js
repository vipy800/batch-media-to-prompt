/* 全能媒体反推 · 前端逻辑 */
const S = {
  cfg: {}, presets: [], models: [], files: [], mode: "auto", tab: "upload",
  jobId: null, timer: null, items: [], itemMap: new Map(), filter: "all",
  job: null, pendingUpload: false, lastSig: "",
};
const $ = (id) => document.getElementById(id);
const money = (n) => (n || 0).toLocaleString("zh-CN");
function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function toast(msg, kind = "", ms = 0) {
  const d = document.createElement("div");
  d.className = "toast " + kind;
  d.textContent = msg;
  $("toasts").appendChild(d);
  setTimeout(() => { d.style.opacity = 0; setTimeout(() => d.remove(), 260); }, ms || (kind === "bad" ? 5200 : 3200));
}

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json().catch(() => ({})) : await res.text();
  if (!res.ok) throw new Error((body && body.detail) || body || `HTTP ${res.status}`);
  return body;
}

/* ---------------- 启动 ---------------- */
async function boot() {
  const b = await api("/api/bootstrap");
  S.cfg = b.config; S.presets = b.presets; S.models = b.models;
  S.cachedModels = b.model_cache || [];
  if (S.cachedModels.length) { CATALOG = S.cachedModels; applyCatalog(CATALOG.map((m) => m.id)); }
  $("ver").textContent = "v" + b.version;
  applyTheme(b.config.theme || "dark");
  renderStats(b.stats);
  renderPresetsUI();
  renderProviders();
  renderModels();
  fillSettings(b.config);
  renderApiState(b.config.has_key);
  $("concRange").value = b.config.concurrency || 3;
  $("concVal").textContent = b.config.concurrency || 3;
  $("folderHint").textContent = "输出目录：" + b.env.output_dir;
  $("customPrompt").value = localStorage.getItem("mr_custom_prompt") || "";
  $("cpCount").textContent = $("customPrompt").value.trim().length + " 字";
  $("videoPresetRow").hidden = S.mode === "image";
  if (new URLSearchParams(location.search).get("custom")) toggleCustomPrompt(true);
  renderAbout(b.env, b.version);
  if (b.env.first_run) {
    setTimeout(() => {
      $("settingsModal").hidden = false;
      toast("首次使用：填好 API Key 并点「测试连接」，就能开始反推", "warn", 6000);
    }, 400);
  } else if (location.search.includes("settings")) {
    setTimeout(() => {
      $("settingsModal").hidden = false;
      const tp = new URLSearchParams(location.search).get("tab");
      const btn = tp && document.querySelector(`.stab[data-stab="${tp}"]`);
      if (btn) btn.click();
      if (CATALOG.length) renderCatalog();
      autoFetch(800);
    }, 200);
  }
  const m = location.hash.match(/job=([0-9a-f]{6,})/i);
  if (m) watchJob(m[1]);
  if (location.search.includes("selfcheck")) {
    setTimeout(() => {
      $("settingsModal").hidden = false;
      const btn = document.querySelector('.stab[data-stab="check"]');
      if (btn) btn.click();
      runSelfCheck();
    }, 600);
  }
}

function renderApiState(hasKey) {
  const el = $("apiState");
  el.className = "pill " + (hasKey ? "ok" : "bad");
  el.innerHTML = `<i class="dot"></i> ${hasKey ? "接口已配置" : "未配置 API Key"}`;
}

function renderStats(s) {
  if (!s) return;
  $("stJobs").textContent = money(s.jobs);
  $("stDone").textContent = money(s.done);
  $("stFail").textContent = money(s.failed);
  $("stChars").textContent = money(s.chars);
}

function renderModels() {
  $("modelList").innerHTML = S.models.map((m) => `<option value="${esc(m)}">`).join("");
}

function groupedOptions(list, selected) {
  const groups = [...new Set(list.map((p) => p.group || "其他"))];
  return groups.map((g) => {
    const items = list.filter((p) => (p.group || "其他") === g);
    return `<optgroup label="${esc(g)}">` + items.map((p) =>
      `<option value="${esc(p.id)}"${p.id === selected ? " selected" : ""}>${esc(p.name)}</option>`).join("") + `</optgroup>`;
  }).join("");
}

function renderPresetsUI() {
  const imgs = S.presets.filter((p) => p.kind !== "video");
  const vids = S.presets.filter((p) => p.kind === "video");
  $("presetSel").innerHTML = groupedOptions(imgs, S.cfg.active_preset_image || "standard");
  $("videoPresetSel").innerHTML = groupedOptions(vids, S.cfg.active_preset_video || "video");
  $("modelInput").value = S.cfg.model || "";
}

/* 自定义提示词：临时用自己写的，不影响预设 */
function toggleCustomPrompt(on) {
  const box = $("customPromptBox");
  const show = on === undefined ? box.hidden : !!on;
  box.hidden = !show;
  $("btnCustomPrompt").classList.toggle("on", show);
  if (show) {
    if (!$("customPrompt").value.trim() && S.cfg.custom_prompt) {
      $("customPrompt").value = S.cfg.custom_prompt;
    }
    $("cpCount").textContent = $("customPrompt").value.trim().length + " 字";
    $("customPrompt").focus();
  }
}
$("btnCustomPrompt").onclick = () => toggleCustomPrompt();
$("customPrompt").addEventListener("input", () => {
  $("cpCount").textContent = $("customPrompt").value.trim().length + " 字";
});
$("btnSaveAsPreset").onclick = () => {
  const text = $("customPrompt").value.trim();
  if (!text) return toast("先写点内容再存", "warn");
  $("savePresetRow").hidden = false;
  $("newPresetName").value = "我的自定义提示词";
  $("newPresetName").focus();
};
$("btnCancelSave").onclick = () => { $("savePresetRow").hidden = true; };
$("btnConfirmSave").onclick = async () => {
  const text = $("customPrompt").value.trim();
  const name = ($("newPresetName").value || "").trim().slice(0, 20);
  if (!text) return toast("先写点内容再存", "warn");
  if (!name) return toast("给预设起个名字", "warn");
  try {
    const r = await api("/api/presets", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", name, text, kind: "image" }),
    });
    S.presets = r.presets;
    renderPresetsUI();
    const saved = S.presets.find((p) => p.name === name && p.builtin === false);
    if (saved) $("presetSel").value = saved.id;
    $("savePresetRow").hidden = true;
    toast("已存为预设，下次可直接选");
  } catch (e) { toast("保存失败：" + e.message, "bad"); }
};

/* ---------------- 主题 ---------------- */
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t === "light" ? "light" : "dark");
  S.cfg.theme = t;
}

/* ---------------- 标签页 / 模式 ---------------- */
document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
  document.querySelectorAll(".tabpane").forEach((x) => x.classList.remove("on"));
  b.classList.add("on");
  $("pane-" + b.dataset.tab).classList.add("on");
  S.tab = b.dataset.tab;
});
document.querySelectorAll("#modeSeg button").forEach((b) => b.onclick = () => {
  document.querySelectorAll("#modeSeg button").forEach((x) => x.classList.remove("on"));
  b.classList.add("on"); S.mode = b.dataset.mode;
  $("videoPresetRow").hidden = S.mode === "image";
});

/* ---------------- 文件选择 ---------------- */
function addFiles(list) {
  const allowed = /\.(jpe?g|png|bmp|tiff?|webp|gif|mp4|avi|mov|mkv|webm|flv|wmv|m4v)$/i;
  for (const f of list) {
    if (!allowed.test(f.name)) { toast(`已跳过不支持的文件：${f.name}`, "warn"); continue; }
    if (S.files.some((x) => x.name === f.name && x.size === f.size)) continue;
    S.files.push(f);
  }
  renderFileList();
}

function renderFileList() {
  const box = $("fileList");
  box.innerHTML = "";
  S.files.slice(0, 200).forEach((f, i) => {
    const d = document.createElement("div");
    d.className = "fitem";
    d.innerHTML = `<span class="nm">${esc(f.name)}</span><span>${fmtSize(f.size)}</span><span class="rm" data-i="${i}">✕</span>`;
    box.appendChild(d);
  });
  box.querySelectorAll(".rm").forEach((el) => el.onclick = (e) => {
    S.files.splice(+e.target.dataset.i, 1); renderFileList();
  });
  $("startHint").textContent = S.files.length ? `已选择 ${S.files.length} 个文件` : "";
}

function fmtSize(n) {
  if (n < 1024) return n + "B";
  if (n < 1048576) return (n / 1024).toFixed(1) + "KB";
  return (n / 1048576).toFixed(1) + "MB";
}

$("drop").onclick = (e) => { if (e.target.id !== "fileInput") $("fileInput").click(); };
$("pick").onclick = () => $("fileInput").click();
$("fileInput").onchange = (e) => { addFiles(e.target.files); e.target.value = ""; };
["dragenter", "dragover"].forEach((ev) => $("drop").addEventListener(ev, (e) => { e.preventDefault(); $("drop").classList.add("hot"); }));
["dragleave", "drop"].forEach((ev) => $("drop").addEventListener(ev, (e) => { e.preventDefault(); $("drop").classList.remove("hot"); }));
$("drop").addEventListener("drop", (e) => addFiles(e.dataTransfer.files));
$("btnClearFiles").onclick = () => { S.files = []; renderFileList(); };

$("concRange").oninput = (e) => { $("concVal").textContent = e.target.value; };

/* ---------------- 开始任务 ---------------- */
$("btnStart").onclick = async () => {
  if (S.pendingUpload) return;
  const conc = $("concRange").value;
  const preset = $("presetSel").value;
  const videoPreset = $("videoPresetSel").value;
  const model = $("modelInput").value.trim();
  const opts = { preset_id: preset, video_preset_id: videoPreset, model, mode: S.mode, concurrency: conc, save_next_to_source: $("optSource").checked ? "1" : "0", skip_existing: $("optSkip").checked ? "1" : "0" };
  const custom = $("customPromptBox").hidden ? "" : $("customPrompt").value.trim();
  if (custom) {
    opts.prompt = custom;
    if ($("customPromptVideo").checked) opts.video_prompt = custom;
    localStorage.setItem("mr_custom_prompt", custom);
  }

  try {
    if (S.tab === "upload") {
      if (!S.files.length) return toast("请先选择文件", "warn");
      const fd = new FormData();
      S.files.forEach((f) => fd.append("files", f));
      Object.entries(opts).forEach(([k, v]) => fd.append(k, v));
      S.pendingUpload = true;
      $("btnStart").disabled = true;
      $("btnStart").textContent = "上传中…";
      const job = await uploadWithProgress(fd);
      S.pendingUpload = false;
      $("btnStart").disabled = false;
      $("btnStart").textContent = "开始批量反推";
      S.files = []; renderFileList();
      toast(`已创建任务：${job.total} 个文件`);
      watchJob(job.job_id);
    } else {
      const folder = $("folderPath").value.trim();
      if (!folder) return toast("请填写文件夹路径", "warn");
      const job = await api("/api/jobs/scan", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder, recursive: $("recursive").checked, ...opts }),
      });
      toast(`已创建任务：${job.total} 个文件`);
      watchJob(job.job_id);
    }
  } catch (e) {
    S.pendingUpload = false;
    $("btnStart").disabled = false;
    $("btnStart").textContent = "开始批量反推";
    toast("创建任务失败：" + e.message, "bad");
  }
};

function uploadWithProgress(fd) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) $("btnStart").textContent = `上传中 ${Math.round(e.loaded / e.total * 100)}%`;
    };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch (e) {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(body.detail || `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("网络错误"));
    xhr.send(fd);
  });
}

/* ---------------- 任务轮询 ---------------- */
function watchJob(id) {
  S.jobId = id;
  $("jobCard").hidden = false;
  const g = $("guideCard"); if (g) g.hidden = true;
  clearInterval(S.timer);
  poll();
  S.timer = setInterval(poll, 900);
  $("jobCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function poll() {
  if (!S.jobId) return;
  try {
    const d = await api("/api/jobs/" + S.jobId);
    S.job = d; S.items = d.items;
    renderJob(d);
    renderItems(d.items);
    const st = d.job.status;
    if (["done", "cancelled", "error"].includes(st) && !d.counts.running && !d.counts.pending) {
      clearInterval(S.timer); S.timer = null;
      toast(st === "done" ? "任务完成" : st === "cancelled" ? "任务已取消" : "任务结束（有失败项）",
        st === "done" ? "" : "warn");
    }
  } catch (e) {
    console.warn(e);
  }
}

function renderJob(d) {
  const c = d.counts;
  $("jobName").textContent = d.job.name || "任务";
  const stMap = { running: "运行中", paused: "已暂停", done: "已完成", cancelled: "已取消", error: "有失败", pending: "等待中" };
  $("jobStatus").textContent = stMap[d.job.status] || d.job.status;
  $("jobBar").style.width = d.progress + "%";
  $("jobPct").textContent = d.progress + "%";
  $("jobDone").textContent = c.done + c.skipped;
  $("jobFail").textContent = c.failed;
  $("jobLeft").textContent = c.pending + c.running;
  $("jobEta").textContent = d.eta ? fmtEta(d.eta) : "—";
  $("cAll").textContent = d.items.length;
  $("cDone").textContent = c.done + c.skipped;
  $("cFail").textContent = c.failed;
  $("cRun").textContent = c.running;
  $("btnPause").hidden = d.paused || !["running"].includes(d.job.status);
  $("btnResume").hidden = !d.paused;
  $("btnRetry").disabled = c.failed === 0;
  document.title = d.job.status === "running" ? `[${d.progress}%] 全能媒体反推` : "全能媒体反推 · 商用版";
}

function fmtEta(s) {
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m" + (s % 60) + "s";
  return Math.floor(s / 3600) + "h" + Math.floor((s % 3600) / 60) + "m";
}

/* ---------------- 结果列表 ---------------- */
function renderItems(items) {
  const box = $("items");
  const list = items.filter((it) => S.filter === "all" ? true : (S.filter === "failed" ? it.status === "failed" : S.filter === "done" ? ["done", "skipped"].includes(it.status) : it.status === S.filter));
  const sig = list.map((it) => `${it.id}:${it.status}:${it.chars}:${it.error || ""}:${it.thumb_url || ""}:${(it.preview || "").slice(0, 30)}`).join("|");
  if (sig === S.lastSig) return;
  S.lastSig = sig;
  const keep = new Set();
  const top = box.scrollTop;
  list.forEach((it) => {
    keep.add(it.id);
    let row = S.itemMap.get(it.id);
    if (!row) {
      row = document.createElement("div");
      row.className = "item";
      row.innerHTML = `<div class="thumbwrap"><img class="th" loading="lazy"><span class="tfb"></span></div><div class="itmain"><div class="nm"></div><div class="meta"></div><div class="pv"></div><div class="errline" hidden></div></div><div class="ops"><button class="ghost b-view">查看</button><button class="ghost b-copy">复制</button><button class="ghost b-rerun">重跑</button></div>`;
      row.onclick = (ev) => { if (!ev.target.closest(".ops")) openItem(it.id); };
      row.querySelector(".b-view").onclick = (ev) => { ev.stopPropagation(); openItem(it.id); };
      row.querySelector(".b-copy").onclick = (ev) => { ev.stopPropagation(); copyItem(it.id); };
      row.querySelector(".b-rerun").onclick = (ev) => { ev.stopPropagation(); rerunItem(it.id); };
      S.itemMap.set(it.id, row);
    }
    row.querySelector(".nm").textContent = `${it.idx + 1}. ${it.filename}`;
    const badge = `<span class="badge ${it.status}">${({ done: "完成", failed: "失败", running: "处理中", pending: "排队", skipped: "跳过", cancelled: "已取消" })[it.status] || it.status}</span>`;
    row.querySelector(".meta").innerHTML = `${badge}<span>${it.chars || 0} 字</span>${it.duration ? `<span>${it.duration}s</span>` : ""}`;
    const pv = row.querySelector(".pv");
    if (it.preview) {
      pv.textContent = it.preview;
      pv.hidden = false;
    } else {
      pv.hidden = true;
    }
    const err = row.querySelector(".errline");
    if (it.error) { err.hidden = false; err.textContent = it.error; } else { err.hidden = true; }
    const img = row.querySelector(".th");
    const wrap = row.querySelector(".thumbwrap");
    if (it.thumb_url) { if (img.getAttribute("src") !== it.thumb_url) img.src = it.thumb_url; wrap.classList.remove("noimg"); }
    else { img.removeAttribute("src"); wrap.classList.add("noimg"); wrap.querySelector(".tfb").textContent = /\.(mp4|mov|mkv|avi|webm)$/i.test(it.filename) ? "▶" : "▧"; }
    row.dataset.status = it.status;
  });
  // 顺序 + 清理过期节点
  const frag = document.createDocumentFragment();
  list.forEach((it) => frag.appendChild(S.itemMap.get(it.id)));
  box.innerHTML = "";
  box.appendChild(frag);
  box.scrollTop = top;
  for (const [id, node] of S.itemMap) if (!keep.has(id)) { S.itemMap.delete(id); node.remove(); }
}

document.querySelectorAll(".filters .chip").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".filters .chip").forEach((x) => x.classList.remove("on"));
  b.classList.add("on"); S.filter = b.dataset.filter;
  renderItems(S.items);
});

/* ---------------- 结果操作 ---------------- */
async function openItem(id) {
  const it = await api("/api/items/" + id);
  $("imTitle").textContent = it.filename;
  $("imText").value = it.text || "";
  $("imHint").textContent = `${it.status} · ${it.chars || 0} 字 · ${it.duration || 0}s`;
  $("imMeta").innerHTML = `输出：${esc(it.out_path || "—")}<br>错误：${esc(it.error || "无")}`;
  const img = $("imThumb");
  if (it.thumb_url) img.src = it.thumb_url; else img.removeAttribute("src");
  $("imSave").dataset.id = id;
  $("imRerun").dataset.id = id;
  $("itemModal").hidden = false;
}

async function copyItem(id) {
  const it = await api("/api/items/" + id);
  if (!it.text) return toast("该项目还没有结果", "warn");
  await navigator.clipboard.writeText(it.text);
  toast("已复制到剪贴板");
}

async function rerunItem(id) {
  try {
    await api(`/api/items/${id}/rerun`, { method: "POST" });
    toast("已重新提交");
    setTimeout(poll, 1200);
  } catch (e) { toast("重跑失败：" + e.message, "bad"); }
}

$("imCopy").onclick = async () => {
  const t = $("imText").value;
  await navigator.clipboard.writeText(t);
  toast("已复制");
};
$("imSave").onclick = async () => {
  const id = $("imSave").dataset.id;
  await api(`/api/items/${id}/text`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: $("imText").value }),
  });
  toast("已保存");
  poll();
};
$("imRerun").onclick = () => rerunItem(+$("imRerun").dataset.id);

/* ---------------- 任务控制 ---------------- */
$("btnPause").onclick = () => api(`/api/jobs/${S.jobId}/pause`, { method: "POST" }).then(poll);
$("btnResume").onclick = () => api(`/api/jobs/${S.jobId}/resume`, { method: "POST" }).then(poll);
$("btnCancel").onclick = () => {
  if (!confirm("确定取消当前任务？已完成的项会保留。")) return;
  api(`/api/jobs/${S.jobId}/cancel`, { method: "POST" }).then(poll);
};
$("btnRetry").onclick = async () => {
  const r = await api(`/api/jobs/${S.jobId}/retry`, { method: "POST" });
  toast(`已重新提交 ${r.count} 个失败项`);
  if (!S.timer) watchJob(S.jobId); else poll();
};
$("btnExportZip").onclick = () => download(`/api/jobs/${S.jobId}/export?fmt=txt`);
$("btnExportCsv").onclick = () => download(`/api/jobs/${S.jobId}/export?fmt=csv`);
$("btnOpenOut").onclick = async () => {
  const p = (S.job && S.job.job && S.job.job.params && S.job.job.params.output_dir) || "";
  try { await api("/api/open-output", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: p }) }); }
  catch (e) { toast(e.message, "bad"); }
};
function download(url) {
  const a = document.createElement("a");
  a.href = url; a.rel = "noopener"; a.click();
}

/* ---------------- 文件夹浏览 ---------------- */
$("btnPickFolder").onclick = async () => {
  try {
    const r = await api("/api/pick-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "folder" }) });
    if (r.path) {
      $("folderPath").value = r.path;
      const info = await api("/api/jobs/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: r.path, recursive: $("recursive").checked }) });
      $("folderHint").textContent = `发现 ${info.total} 个文件（图片 ${info.images} / 视频 ${info.videos}）`;
    }
  } catch (e) { toast("无法打开选择器：" + e.message, "bad"); }
};
$("folderPath").onblur = async () => {
  const p = $("folderPath").value.trim();
  if (!p) return;
  try {
    const info = await api("/api/jobs/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: p, recursive: $("recursive").checked }) });
    $("folderHint").textContent = `发现 ${info.total} 个文件（图片 ${info.images} / 视频 ${info.videos}）`;
  } catch (e) { $("folderHint").textContent = e.message; }
};

/* ---------------- 设置 ---------------- */
function fillSettings(c) {
  $("cfgKey").value = "";
  $("cfgKey").placeholder = c.has_key
    ? `已保存 ${c.api_key_masked || "Key"}，留空保持不变`
    : "sk-...";
  if ($("btnClearKey")) $("btnClearKey").hidden = !c.has_key;
  $("cfgBase").value = c.base_url || "";
  $("cfgModel").value = c.model || "";
  $("cfgVideoModel").value = c.video_model || "";
  $("cfgMaxSide").value = c.image_max_side;
  $("cfgQuality").value = c.jpeg_quality;
  $("cfgFrames").value = c.video_frames;
  $("cfgVidSide").value = c.video_max_side;
  $("cfgGrid").checked = c.video_grid !== false;
  $("cfgConc").value = c.concurrency;
  $("cfgTimeout").value = c.timeout;
  $("cfgRetries").value = c.max_retries;
  $("cfgOutput").value = c.output_folder || "";
  $("presetManage").innerHTML = groupedOptions(
    S.presets.map((p) => ({ ...p, name: p.name + (p.builtin === false ? "" : "（内置）") })), null);
  loadPresetIntoEditor(S.presets[0]);
}

document.querySelectorAll(".stab").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".stab").forEach((x) => x.classList.remove("on"));
  document.querySelectorAll(".stabpane").forEach((x) => x.classList.remove("on"));
  b.classList.add("on"); $("stab-" + b.dataset.stab).classList.add("on");
});

/* 本地接口：端口快捷填入 + 一键探测 */
document.querySelectorAll("[data-timeout]").forEach((b) => b.onclick = () => {
  $("cfgTimeout").value = b.dataset.timeout;
  toast(`超时已设为 ${b.dataset.timeout} 秒，记得点「保存设置」`);
});
document.querySelectorAll("[data-port]").forEach((b) => b.onclick = () => {
  const port = b.dataset.port;
  $("cfgBase").value = `http://127.0.0.1:${port}/v1`;
  toast(`已填入 http://127.0.0.1:${port}/v1，本地接口留空 Key 也能跑`);
});

$("btnProbeLocal").onclick = async () => {
  const hint = $("probeHint");
  hint.hidden = false;
  hint.textContent = "正在扫描 127.0.0.1 上的常见 AI 服务…";
  try {
    const r = await api("/api/local/scan");
    const found = r.found || [];
    if (!found.length) {
      hint.textContent = "没找到本地服务：确认 Ollama / LM Studio / llama.cpp 已启动，并把上面的端口点一下手动填。";
      toast("未检测到本地服务", "warn", 5000);
      return;
    }
    const first = found[0];
    $("cfgBase").value = first.url;
    if (first.models && first.models.length) {
      $("cfgModel").value = first.models[0];
      $("cfgVideoModel").value = first.models[0];
    }
    hint.textContent = found.map((f) => `${f.name} ${f.url}（${f.models.length} 个模型：${f.models.slice(0, 3).join("、") || "未命名"}）`).join(" ｜ ");
    toast(`已填入 ${first.name} ${first.url}`, "ok", 4500);
  } catch (e) {
    hint.textContent = "检测失败：" + e.message;
    toast("检测失败：" + e.message, "bad");
  }
};

$("btnSettings").onclick = () => {
  fillSettings(S.cfg);
  $("settingsModal").hidden = false;
  if (CATALOG.length) renderCatalog();
  autoFetch(500);
};

/* 服务商快捷填充（含注册福利链接） */
const PROVIDERS = [
  {
    id: "siliconflow", name: "硅基流动", tag: "送 16 元", badge: "模型全",
    desc: "Qwen3-VL 等视觉模型齐全，出词稳定",
    base: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen3-VL-32B-Instruct",
    link: "https://cloud.siliconflow.cn/i/9VTziPIQ", linkText: "注册领 16 元额度",
  },
  {
    id: "zhipu", name: "智谱 AI", tag: "送 2 亿 Tokens", badge: "GLM-5.3",
    desc: "GLM-5.3-Flash 原生多模态，1M 上下文",
    base: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5.3-flash",
    link: "https://www.bigmodel.cn/invite?icode=XG%2FAr2D7pjbGwf3MI83HHWczbXFgPRGIalpycrEwJ28%3D",
    linkText: "注册领 2 亿 Tokens",
  },
  {
    id: "modelscope", name: "魔塔社区", tag: "送 50 魔力", badge: "每天送 200",
    desc: "ModelScope 推理 API，日常用量够用",
    base: "https://api-inference.modelscope.cn/v1", model: "Qwen/Qwen3-VL-32B-Instruct",
    link: "https://www.modelscope.cn/register?inviteCode=asy666&invitorName=asy666",
    linkText: "注册领 50 魔力",
  },
  {
    id: "qiniu", name: "七牛云", tag: "送 300 万 Token", badge: "模型全",
    desc: "Qwen4-Max 图文视频通吃，办公够用",
    base: "https://api.qnaigc.com/v1", model: "qwen/qwen4-max",
    link: "https://s.qiniu.com/eEJNBn", linkText: "注册领 300 万 Token",
  },
  {
    id: "generic", name: "通用接口", tag: "自定义", badge: "任意兼容",
    desc: "任何 OpenAI 兼容服务商，自己填地址",
    base: "", model: "",
  },
  {
    id: "local", name: "本地 AI 通用接口", tag: "免费 · 离线 · 免 Key", badge: "任意端口",
    desc: "Ollama / LM Studio / llama.cpp / vLLM，端口随你填",
    base: "http://127.0.0.1:11434/v1", model: "qwen2.5vl:7b",
  },
];

function renderProviders() {
  const box = $("provGrid");
  if (!box) return;
  box.innerHTML = PROVIDERS.map((p) => `
    <div class="prov" data-prov="${p.id}">
      <div class="ptop"><b>${p.name}</b><span class="ptag">${p.tag}</span></div>
      <div class="pdesc">${p.desc}</div>
      <div class="pbase" title="${p.base}${p.model ? " · " + p.model : ""}">${p.base ? p.base.replace(/^https?:\/\//, "") : "服务商提供的 /v1 地址"}</div>
      ${p.link ? `<a class="plink" href="${p.link}" target="_blank" rel="noopener noreferrer">${p.linkText} ↗</a>` : `<span class="plink none">${p.id === "local" ? "本地模型无需注册" : "自备接口与密钥"}</span>`}
    </div>`).join("");
  box.querySelectorAll(".prov").forEach((el) => {
    el.onclick = (ev) => {
      if (ev.target.closest(".plink")) return;   // 点链接不覆盖表单
      const p = PROVIDERS.find((x) => x.id === el.dataset.prov);
      box.querySelectorAll(".prov").forEach((x) => x.classList.remove("on"));
      el.classList.add("on");
      $("cfgBase").value = p.base;
      $("cfgModel").value = p.model;
      $("cfgVideoModel").value = p.model;
      CATALOG = [];
      $("modelBox").hidden = true;
      $("modelHint").textContent = "填好 Key / 地址会自动检测";
      $("modelHint").style.color = "";
      if (p.id === "generic") {
        $("cfgBase").value = "";
        $("cfgModel").value = "";
        $("cfgVideoModel").value = "";
        $("cfgBase").focus();
        toast("填服务商给的 Base URL（一般以 /v1 结尾），再填模型名和 Key", "warn", 5000);
      } else if (p.id === "local") {
        toast("本地地址默认 11434（Ollama）；LM Studio 改 1234，llama.cpp 改 8080", "ok", 5000);
        autoFetch(300);
      } else {
        toast(`已填入「${p.name}」，模型 ${p.model}，去填 Key 即可`, "ok");
        autoFetch(300);
      }
    };
  });
}
$("btnTheme").onclick = () => {
  applyTheme(S.cfg.theme === "light" ? "dark" : "light");
  api("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ theme: S.cfg.theme }) }).catch(() => {});
};
$("btnSaveCfg").onclick = async () => {
  const patch = {
    base_url: $("cfgBase").value.trim(),
    model: $("cfgModel").value.trim(),
    video_model: $("cfgVideoModel").value.trim(),
    image_max_side: +$("cfgMaxSide").value,
    jpeg_quality: +$("cfgQuality").value,
    video_frames: +$("cfgFrames").value,
    video_max_side: +$("cfgVidSide").value,
    video_grid: $("cfgGrid").checked,
    concurrency: +$("cfgConc").value,
    timeout: +$("cfgTimeout").value,
    max_retries: +$("cfgRetries").value,
    output_folder: $("cfgOutput").value.trim(),
  };
  const typedKey = $("cfgKey").value.trim();
  if (typedKey) patch.api_key = typedKey;
  try {
    const r = await api("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
    S.cfg = r.config;
    fillSettings(S.cfg);
    renderApiState(S.cfg.has_key);
    renderPresetsUI();
    $("saveHint").textContent = "已保存 " + new Date().toLocaleTimeString();
    toast("设置已保存");
    if (S.cfg.has_key || isLocalBase(S.cfg.base_url)) autoFetch(400);
  } catch (e) { toast("保存失败：" + e.message, "bad"); }
};

$("btnClearKey") && ($("btnClearKey").onclick = async () => {
  if (!confirm("清除本机保存的 API Key？清除后云端接口将无法运行。")) return;
  try {
    const r = await api("/api/config/clear-key", { method: "POST" });
    S.cfg = r.config;
    fillSettings(S.cfg);
    renderApiState(S.cfg.has_key);
    toast("已清除 API Key", "warn");
  } catch (e) { toast("清除失败：" + e.message, "bad"); }
});

$("btnTest").onclick = async () => {
  $("testResult").textContent = "测试中…";
  try {
    const body = {
      base_url: $("cfgBase").value.trim(),
      model: $("cfgModel").value.trim(),
    };
    const typedKey = $("cfgKey").value.trim();
    if (typedKey) body.api_key = typedKey;   // 留空则用后端已保存的 Key
    const r = await api("/api/config/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("testResult").textContent = r.ok ? `连接成功（${r.ms}ms）：${r.reply}` : `失败：${r.error}`;
    $("testResult").style.color = r.ok ? "var(--ok)" : "var(--danger)";
  } catch (e) { $("testResult").textContent = e.message; }
};

/* ---------------- 模型自动发现 ---------------- */
let CATALOG = [];
let catalogTimer = null;

function isLocalBase(b) {
  const raw = String(b || "").trim();
  if (!raw) return false;
  try {
    const u = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : "http://" + raw);
    const host = u.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (["127.0.0.1", "localhost", "0.0.0.0", "::1"].includes(host)) return true;
    if (host.startsWith("192.168.") || host.startsWith("10.")) return true;
    const m = host.match(/^172\.(\d+)\./);
    return !!m && +m[1] >= 16 && +m[1] <= 31;
  } catch (e) { return false; }
}

function renderCatalog(rec) {
  const box = $("modelBox");
  const q = ($("modelFilter").value || "").trim().toLowerCase();
  const list = CATALOG.filter((m) => !q || m.id.toLowerCase().includes(q));
  $("modelFilter").hidden = CATALOG.length < 8;
  box.hidden = false;
  if (!list.length) {
    box.innerHTML = `<div class="mrow"><span class="mid">${CATALOG.length ? "没有匹配的模型" : "没拉到模型，可直接手填模型名"}</span></div>`;
    return;
  }
  box.innerHTML = list.map((m) => `
    <div class="mrow">
      <span class="mid" title="${esc(m.id)}">${esc(m.id)}</span>
      ${m.vision ? `<span class="vtag">视觉</span>` : `<span class="ntag">文本</span>`}
      ${m.rec ? `<span class="ntag">推荐</span>` : ""}
      <button class="${$("cfgModel").value.trim() === m.id ? "on" : ""}" data-mid="${esc(m.id)}" data-act="img">图片</button>
      <button class="${$("cfgVideoModel").value.trim() === m.id ? "on" : ""}" data-mid="${esc(m.id)}" data-act="vid">视频</button>
    </div>`).join("");
  box.querySelectorAll("button").forEach((b) => b.onclick = () => {
    const id = b.dataset.mid;
    if (b.dataset.act === "img") {
      $("cfgModel").value = id;
      if (!CATALOG.some((m) => m.id === $("cfgVideoModel").value.trim())) $("cfgVideoModel").value = id;
    } else {
      $("cfgVideoModel").value = id;
      if (!CATALOG.some((m) => m.id === $("cfgModel").value.trim())) $("cfgModel").value = id;
    }
    toast(`已选模型 ${id}，点「保存设置」生效`, "ok", 4000);
    renderCatalog();
  });
}

function applyCatalog(ids) {
  const merged = [...new Set([...ids, ...CATALOG.map((m) => m.id)])];
  $("modelList").innerHTML = merged.map((m) => `<option value="${esc(m)}">`).join("");
  S.models = merged;
}

function autoPickVision() {
  if (!CATALOG.length) return;
  const known = (v) => CATALOG.some((m) => m.id === (v || "").trim());
  const best = CATALOG.filter((m) => m.vision)[0] || CATALOG[0];
  if (!known($("cfgModel").value)) {
    $("cfgModel").value = best.id;
    if (!known($("cfgVideoModel").value)) $("cfgVideoModel").value = best.id;
    $("modelHint").textContent = `已自动选中最合适的视觉模型：${best.id}（记得保存）`;
  }
}

async function fetchModels(silent) {
  const base = $("cfgBase").value.trim();
  const key = $("cfgKey").value.trim();
  if (!base) {
    if (!silent) $("modelHint").textContent = "先填接口地址，再拉模型";
    return;
  }
  if (catalogTimer) clearTimeout(catalogTimer);
  $("modelHint").textContent = "正在拉取模型列表…";
  $("btnFetchModels").disabled = true;
  try {
    const payload = { base_url: base };
    if (key) payload.api_key = key;
    const r = await api("/api/models", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (r.ok) {
      CATALOG = r.models || [];
      $("modelFilter").value = "";
      applyCatalog(CATALOG.map((m) => m.id));
      renderCatalog();
      $("modelHint").textContent = `已拉取 ${r.count} 个模型，其中 ${r.vision_count} 个支持视觉（标「视觉」的才能反推图片/视频）`;
      autoPickVision();
      $("modelHint").style.color = "var(--ok)";
    } else {
      CATALOG = (r.suggestions || []).map((id) => ({ id, vision: true, rec: true }));
      applyCatalog(CATALOG.map((m) => m.id));
      renderCatalog();
      $("modelHint").textContent = r.error + "；下面列出推荐模型";
      $("modelHint").style.color = "var(--warn, #f59e0b)";
      if (!silent) toast(r.error, "warn", 5000);
    }
  } catch (e) {
    if (!silent) {
      $("modelHint").textContent = "拉取失败：" + e.message;
      $("modelHint").style.color = "var(--danger)";
    }
  } finally {
    $("btnFetchModels").disabled = false;
  }
}

const autoFetch = (() => {
  let t = null;
  return (ms) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => {
      const base = $("cfgBase").value.trim();
      const key = $("cfgKey").value.trim();
      if (base && (key || S.cfg.has_key || isLocalBase(base))) fetchModels(true);
    }, ms);
  };
})();

$("btnFetchModels").onclick = () => fetchModels(false);
$("modelFilter").oninput = () => renderCatalog();
$("cfgBase").addEventListener("blur", () => autoFetch(600));
$("cfgKey").addEventListener("blur", () => autoFetch(600));
$("cfgKey").addEventListener("input", () => { if ($("cfgKey").value.trim().length > 20) autoFetch(1200); });
$("cfgBase").addEventListener("input", () => autoFetch(1200));

$("btnPickOutput").onclick = async () => {
  try {
    const r = await api("/api/pick-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "folder" }) });
    if (r.path) $("cfgOutput").value = r.path;
  } catch (e) { toast(e.message, "bad"); }
};

/* ---------------- 一键自检 ---------------- */
async function runSelfCheck() {
  const box = $("checkList");
  const sum = $("checkSummary");
  box.innerHTML = "";
  sum.className = "hint";
  sum.textContent = "正在自检：会真实请求一次接口和一次看图，稍等…";
  $("btnSelfCheck").disabled = true;
  try {
    const r = await api("/api/selfcheck", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deep: true }),
    });
    box.innerHTML = (r.checks || []).map((c) => {
      const cls = c.ok ? (c.level === "warn" ? "warn" : "ok") : (c.level === "info" ? "warn" : "bad");
      const ico = c.ok ? "✓" : (c.level === "info" ? "!" : "✗");
      return `<div class="chk ${cls}">
        <div class="ico">${ico}</div>
        <div class="ct"><b>${esc(c.name)}</b><div class="cd">${esc(c.detail || "")}</div>
        ${c.fix && !c.ok ? `<div class="cf">修法：${esc(c.fix)}</div>` : ""}</div>
      </div>`;
    }).join("");
    const total = r.checks.length;
    sum.className = r.ok ? "hint ok" : "hint bad";
    sum.textContent = r.ok
      ? `全部通过（${total} 项）——可以直接开跑批量任务了`
      : `有 ${r.failed} 项没通过，按下面「修法」改完再自检一次`;
  } catch (e) {
    sum.className = "hint bad";
    sum.textContent = "自检请求失败：" + e.message;
  } finally {
    $("btnSelfCheck").disabled = false;
  }
}
$("btnSelfCheck").onclick = runSelfCheck;

/* ---------------- 预设管理 ---------------- */
$("presetManage").onchange = () => {
  const p = S.presets.find((x) => x.id === $("presetManage").value);
  if (p) loadPresetIntoEditor(p);
};
function loadPresetIntoEditor(p) {
  if (!p) return;
  $("presetName").value = p.name;
  $("presetKind").value = p.kind === "video" ? "video" : "image";
  $("presetText").value = p.text || "";
  $("btnPresetDel").disabled = p.builtin !== false;
}
$("btnPresetNew").onclick = () => {
  $("presetManage").value = "";
  $("presetName").value = "新预设";
  $("presetText").value = "";
  $("presetKind").value = "image";
  $("btnPresetDel").disabled = true;
};
$("btnPresetDel").onclick = async () => {
  const id = $("presetManage").value;
  if (!id || !confirm("删除该自定义预设？")) return;
  const r = await api("/api/presets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "delete", id }) });
  S.presets = r.presets; fillSettings(S.cfg); renderPresetsUI();
  toast("已删除");
};
// 保存自定义预设：名称改动即保存
$("presetName").addEventListener("change", async () => {
  if (!$("presetText").value.trim()) return;
  const r = await api("/api/presets", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "save", id: $("presetManage").value || null, name: $("presetName").value, kind: $("presetKind").value, text: $("presetText").value }),
  });
  S.presets = r.presets;
  renderPresetsUI();
  $("presetManage").innerHTML = groupedOptions(
    S.presets.map((p) => ({ ...p, name: p.name + (p.builtin === false ? "" : "（内置）") })), null);
  const saved = S.presets.find((p) => p.name === $("presetName").value);
  if (saved) $("presetManage").value = saved.id;
  $("btnPresetDel").disabled = !saved || saved.builtin !== false;
  toast("预设已保存");
});
$("presetText").addEventListener("change", () => $("presetName").dispatchEvent(new Event("change")));
$("presetKind").addEventListener("change", () => $("presetName").dispatchEvent(new Event("change")));

/* ---------------- 历史 ---------------- */
$("btnHistory").onclick = () => { $("historyModal").hidden = false; loadHistory(); };
$("btnRefreshH").onclick = loadHistory;
$("btnHQuery").onclick = loadHistory;
$("hq").onkeydown = (e) => { if (e.key === "Enter") loadHistory(); };

async function loadHistory() {
  const r = await api("/api/history?q=" + encodeURIComponent($("hq").value.trim()));
  const box = $("historyList");
  box.innerHTML = r.jobs.length ? "" : `<p class="hint">暂无历史任务</p>`;
  r.jobs.forEach((j) => {
    const d = document.createElement("div");
    d.className = "hitem";
    const t = new Date(j.created_at * 1000).toLocaleString("zh-CN");
    d.innerHTML = `<div><div class="nm">${esc(j.name)}</div><div class="meta"><span>${esc(t)}</span><span>${esc(j.model || "")}</span><span>完成 ${j.done || 0} / 失败 ${j.failed || 0}</span><span>${esc(j.status)}</span></div></div>
      <div class="ops"><button class="ghost b-open">查看</button><button class="ghost danger b-del">删除</button></div>`;
    d.querySelector(".b-open").onclick = () => { $("historyModal").hidden = true; watchJob(j.id); };
    d.querySelector(".b-del").onclick = async () => {
      if (!confirm("删除该任务记录？")) return;
      try {
        await api("/api/jobs/" + j.id, { method: "DELETE" });
        loadHistory(); toast("已删除");
      } catch (e) { toast("删除失败：" + e.message, "bad"); }
    };
    box.appendChild(d);
  });
  renderStats(r.stats);
}

/* ---------------- 运维 ---------------- */
$("btnClean").onclick = async () => {
  const r = await api("/api/maintenance/clean-uploads", { method: "POST" });
  toast("已清理，剩余缓存 " + r.size);
};
$("btnClearHistory").onclick = async () => {
  if (!confirm("清空所有历史记录（不影响已导出的文本文件）？")) return;
  try {
    const r = await api("/api/history/clear", { method: "POST" });
    toast(`已清空 ${r.deleted} 条`);
    renderStats({ jobs: 0, done: 0, failed: 0, pending: 0, chars: 0 });
  } catch (e) { toast("清空失败：" + e.message, "bad"); }
};
$("btnLogs").onclick = async () => {
  const box = $("logBox");
  box.hidden = false;
  box.textContent = (await fetch("/api/logs?lines=400").then((r) => r.text())) || "暂无日志";
};

function renderAbout(env, version) {
  $("aboutBox").innerHTML = `
    <div><b>版本</b> v${esc(version)} · 商用版</div>
    <div><b>运行方式</b> ${env.frozen ? "免安装打包版" : "源码版"}</div>
    <div><b>Python</b> ${esc(env.python)}　<b>系统</b> ${esc(env.platform)}</div>
    <div><b>数据目录</b> ${esc(env.base_dir)}</div>
    <div><b>输出目录</b> ${esc(env.output_dir)}</div>
    <div><b>数据库</b> ${esc(env.db)}</div>
    <div class="aboutlinks">
      <b>资源与开源</b>
      <div>搜源站　<a href="https://www.souyuanzhan.com/" target="_blank" rel="noopener">https://www.souyuanzhan.com/</a></div>
      <div>资源汇　<a href="https://viptu.cn/" target="_blank" rel="noopener">https://viptu.cn/</a></div>
      <div>开源地址　<a href="https://viptu.cn/" target="_blank" rel="noopener">https://viptu.cn/</a></div>
    </div>`;
}

/* ---------------- 弹窗通用 ---------------- */
document.querySelectorAll("[data-close]").forEach((b) => b.onclick = (e) => { e.target.closest(".modal").hidden = true; });
document.querySelectorAll(".modal").forEach((m) => m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; }));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".modal").forEach((m) => m.hidden = true);
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") { e.preventDefault(); if (!$("pane-upload").classList.contains("on")) document.querySelector('.tab[data-tab="upload"]').click(); $("fileInput").click(); }
});

boot().catch((e) => toast("初始化失败：" + e.message + "（请检查后端是否启动）", "bad"));
