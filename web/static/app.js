/* 课程工单 Agent 前端逻辑 */
const $ = (id) => document.getElementById(id);

const STATUS = {
  auto_answered: ["已自动答复", "auto_answered"],
  auto_closed: ["已自动归档", "auto_closed"],
  routed: ["已分类 · 转人工", "routed"],
  pending_review: ["待人工复核", "pending_review"],
  rejected: ["输入无效 · 已拒绝", "rejected"],
};

const LABEL_SHORT = {
  homework: "作业疑问",
  system: "系统故障",
  exam: "考试咨询",
  admin: "行政申请",
  other: "无关/灌水",
};

let samples = [];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));
}

function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

async function api(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({ ok: false, error: "响应解析失败" }));
  if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ------------------------- 示例 ------------------------- */
async function loadSamples(prefill = true) {
  try {
    const data = await api("/api/samples");
    samples = data.samples || [];
  } catch (e) {
    samples = ["学习通打不开，一直显示 502 Bad Gateway"];
  }
  const box = $("examples");
  box.innerHTML = "";
  samples.slice(0, 5).forEach((text) => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.textContent = text.length > 16 ? text.slice(0, 16) + "…" : text;
    btn.title = text;
    btn.onclick = () => {
      $("input").value = text;
      updateCount();
      $("input").focus();
    };
    box.appendChild(btn);
  });

  if (prefill) {
    $("input").value = samples[0] || "";
    updateCount();
  }
}

function updateCount() {
  const n = $("input").value.length;
  $("charCount").textContent = `${n} / 500`;
}

/* ------------------------- 提交 ------------------------- */
async function submit() {
  const text = $("input").value.trim();
  if (!text) {
    toast("请先输入一条学生消息");
    return;
  }
  const btn = $("submitBtn");
  btn.disabled = true;
  btn.querySelector("span").textContent = "处理中…";
  try {
    const data = await api("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    renderResult(data.result);
  } catch (e) {
    toast("处理失败：" + e.message);
  } finally {
    btn.disabled = false;
    btn.querySelector("span").textContent = "提交工单";
    refreshStats();
  }
}

function renderResult(r) {
  $("emptyState").classList.add("hidden");
  $("resultBody").classList.remove("hidden");

  const [label, key] = STATUS[r.resolution] || ["已处理", r.resolution];
  const badge = $("statusBadge");
  badge.textContent = label;
  badge.dataset.status = key;
  badge.classList.remove("hidden");

  $("resultSub").textContent = `工单 #${r.ticket_id ?? "—"} · ${r.steps.length} 个处理步骤`;

  $("mLabel").textContent = r.label_cn || LABEL_SHORT[r.label] || "—";
  $("mConf").textContent = (r.confidence * 100).toFixed(1) + "%";
  $("mRoute").textContent = r.route_to || "—";
  $("mPriority").textContent = r.priority || "—";
  $("mTicket").textContent = r.ticket_id ? `#${r.ticket_id}` : "未落库";
  const total = r.steps.reduce((a, s) => a + (s.elapsed_ms || 0), 0);
  $("mLatency").textContent = `${total} ms`;

  const pct = Math.round((r.confidence || 0) * 100);
  $("confText").textContent = pct + "%";
  $("confFill").style.width = pct + "%";

  $("replyText").textContent = r.reply || "（无答复）";

  const list = $("sourcesList");
  list.innerHTML = "";
  if (r.sources && r.sources.length) {
    $("sourcesWrap").classList.remove("hidden");
    r.sources.forEach((s) => {
      const tag = document.createElement("span");
      tag.className = "source-item";
      tag.textContent = `${s.faq_id} · ${s.source} · 相似度 ${s.score.toFixed(2)}`;
      tag.title = s.answer;
      list.appendChild(tag);
    });
  } else {
    $("sourcesWrap").classList.add("hidden");
  }

  renderTrace(r.steps);
  $("jsonView").textContent = JSON.stringify(r, null, 2);
  $("totalMs").textContent = total + " ms";
}

function renderTrace(steps) {
  const box = $("traceList");
  box.innerHTML = "";
  steps.forEach((s, i) => {
    const item = document.createElement("div");
    item.className = "trace-item";
    const icon = { ok: "✓", review: "!", error: "✗" }[s.status] || "·";
    const cls = s.status === "review" ? "review" : s.status === "error" ? "error" : "";
    item.innerHTML = `
      <div class="trace-icon ${cls}">${icon}</div>
      <div>
        <div class="trace-name">${i + 1}. ${esc(s.name)}</div>
        <div class="trace-detail">${esc(s.detail)}</div>
      </div>
      <div class="trace-ms">${s.elapsed_ms} ms</div>`;
    box.appendChild(item);
  });
}

/* ------------------------- 统计 ------------------------- */
async function refreshStats() {
  try {
    const data = await api("/api/stats");
    const s = data.stats || {};
    $("statLine").textContent =
      `工单总数 ${s.total || 0} ｜ 自动答复 ${s.auto_answered || 0} ｜ 自动归档 ${s.auto_closed || 0} ` +
      `｜ 转人工 ${s.routed || 0} ｜ 待复核 ${s.pending_review || 0}`;
    $("reviewCount").textContent = s.pending_review || 0;
  } catch (e) {
    /* 静默失败，不阻塞主流程 */
  }
}

/* ------------------------- 复核队列 ------------------------- */
async function openDrawer() {
  $("drawer").classList.add("open");
  $("overlay").classList.remove("hidden");
  const box = $("reviewList");
  box.innerHTML = '<div class="trace-empty">加载中…</div>';
  try {
    const data = await api("/api/reviews");
    const rows = data.reviews || [];
    box.innerHTML = "";
    if (!rows.length) {
      box.innerHTML = '<div class="trace-empty">暂无待复核工单</div>';
      return;
    }
    rows.forEach((r) => {
      const el = document.createElement("div");
      el.className = "review-item";
      el.innerHTML = `
        <div class="review-top">
          <b>#${r.id} · ${esc(r.label_cn)}</b>
          <span class="muted">置信度 ${(r.confidence * 100).toFixed(1)}%</span>
        </div>
        <div class="review-text">${esc(r.raw_text)}</div>
        <div class="review-reason">${esc(r.review_reason || "人工复核")}</div>
        <div class="review-actions">
          <button class="mini-btn primary" data-id="${r.id}" data-status="resolved">标记已答复</button>
          <button class="mini-btn" data-id="${r.id}" data-status="closed">关闭工单</button>
        </div>`;
      box.appendChild(el);
    });
    box.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.onclick = () => resolveTicket(btn.dataset.id, btn.dataset.status);
    });
  } catch (e) {
    box.innerHTML = `<div class="trace-empty">加载失败：${esc(e.message)}</div>`;
  }
}

async function resolveTicket(id, status) {
  try {
    await api(`/api/reviews/${id}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    toast(status === "resolved" ? "已标记为已答复" : "工单已关闭");
    openDrawer();
    refreshStats();
  } catch (e) {
    toast("操作失败：" + e.message);
  }
}

function closeDrawer() {
  $("drawer").classList.remove("open");
  $("overlay").classList.add("hidden");
}

/* ------------------------- 启动 ------------------------- */
async function init() {
  const initial = window.__INITIAL__;
  if (initial && initial.resolution) {
    $("input").value = initial.raw_text || "";
    updateCount();
    renderResult(initial);
  }

  await loadSamples(!(initial && initial.resolution));
  await refreshStats();

  $("submitBtn").onclick = submit;
  $("reviewBtn").onclick = openDrawer;
  $("closeDrawer").onclick = closeDrawer;
  $("overlay").onclick = closeDrawer;
  $("input").addEventListener("input", updateCount);
  $("input").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit();
  });

  // 服务端预跑模式：用于录屏/截图与无 JS 环境，页面首次渲染即带结果
  if (initial && initial.resolution) return;

  const params = new URLSearchParams(location.search);
  if (params.get("demo")) {
    const text = params.get("text") || samples[0];
    $("input").value = text;
    updateCount();
    setTimeout(submit, 400);
  }
}

init();
