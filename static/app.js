const currency = new Intl.NumberFormat(undefined, {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 2,
});

async function fetchJson(url, options) {
  const timeoutMs = options?.timeoutMs || 20000;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const response = await fetch(url, { ...options, signal: controller.signal });
  window.clearTimeout(timeout);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return await response.json();
}

function asMoney(value) {
  return currency.format(Number(value || 0));
}

function statusClass(status) {
  if (status === "reorder" || status === "critical") return "danger";
  if (status === "watch" || status === "high") return "warn";
  return "ok";
}

function renderOpsStats(overview, operations) {
  const summary = operations.summary || {};
  const cards = [
    ["Expected orders", summary.expected_orders || 0],
    ["Staffing gap", summary.staffing_gap || 0],
    ["Stock alerts", summary.low_stock_count || 0],
    ["Receipt spend", asMoney(overview.totals.total_spend)],
  ];
  document.getElementById("opsStats").innerHTML = cards
    .map(([label, value]) => `
      <article class="kpi-card">
        <span>${label}</span>
        <strong>${value}</strong>
      </article>
    `)
    .join("");
}

function renderPriorities(priorities) {
  const root = document.getElementById("priorityList");
  if (!priorities.length) {
    root.innerHTML = `<p class="muted">No open priorities. Load cafe data to populate the dashboard.</p>`;
    return;
  }
  root.innerHTML = priorities
    .map((item) => `
      <article class="priority-item ${statusClass(item.severity)}">
        <div>
          <strong>${item.title}</strong>
          <p>${item.rationale}</p>
        </div>
        <span>${item.severity}</span>
      </article>
    `)
    .join("");
}

function renderStaffing(rows) {
  const root = document.getElementById("staffingGrid");
  if (!rows.length) {
    root.innerHTML = `<p class="muted">No staffing forecast yet.</p>`;
    return;
  }
  root.innerHTML = rows
    .map((row) => {
      const gap = Math.max(0, row.recommended_staff - row.scheduled_staff);
      return `
        <article class="staff-card ${gap ? "warn" : "ok"}">
          <div class="staff-card-top">
            <strong>${row.daypart}</strong>
            <span>${row.weather}, ${row.temperature_c}C</span>
          </div>
          <div class="staff-counts">
            <span>${row.expected_orders} orders</span>
            <span>${row.scheduled_staff}/${row.recommended_staff} staff</span>
          </div>
          <p>${row.rationale}</p>
        </article>
      `;
    })
    .join("");
}

function renderStock(rows) {
  const body = document.getElementById("stockTable");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="4">No stock data yet.</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((item) => `
      <tr>
        <td>
          <strong>${item.item_name}</strong>
          <small>${item.supplier || "No supplier"}</small>
        </td>
        <td>${item.current_qty} ${item.unit}</td>
        <td>${item.days_left ?? "n/a"}</td>
        <td><span class="tag ${statusClass(item.status)}">${item.status}</span></td>
      </tr>
    `)
    .join("");
}

function renderCalendar(rows) {
  const root = document.getElementById("calendarSignals");
  if (!rows.length) {
    root.innerHTML = `<p class="muted">No calendar signals yet.</p>`;
    return;
  }
  root.innerHTML = rows
    .map((item) => `
      <article class="signal-item">
        <strong>${item.day_name} ${item.business_date}</strong>
        <span>${item.is_weekend ? "Weekend" : "Weekday"}${item.is_holiday ? " / Holiday" : ""}</span>
        <p>${item.note}</p>
      </article>
    `)
    .join("");
}

function renderReceipts(receipts) {
  const body = document.getElementById("receiptsTable");
  if (!receipts.length) {
    body.innerHTML = `<tr><td colspan="4">No receipts yet.</td></tr>`;
    return;
  }
  body.innerHTML = receipts
    .map((receipt) => `
      <tr>
        <td>${receipt.merchant_name}</td>
        <td>${receipt.business_date || "Unknown"}</td>
        <td>${receipt.total == null ? "n/a" : asMoney(receipt.total)}</td>
        <td>${Math.round((receipt.confidence || 0) * 100)}%</td>
      </tr>
    `)
    .join("");
}

async function refreshDashboard() {
  const [dashboard, receipts, health] = await Promise.all([
    fetchJson("/api/dashboard"),
    fetchJson("/api/receipts?limit=12"),
    fetchJson("/api/health"),
  ]);
  document.getElementById("heroHealth").textContent = `Backend ${health.status}`;
  document.getElementById("story").textContent = dashboard.story;
  renderOpsStats(dashboard.overview, dashboard.operations);
  renderPriorities(dashboard.operations.priorities || []);
  renderStaffing(dashboard.operations.staffing || []);
  renderStock(dashboard.operations.stock || []);
  renderCalendar(dashboard.operations.calendar || []);
  renderReceipts(receipts.receipts);
}

document.getElementById("seedButton").addEventListener("click", async () => {
  const button = document.getElementById("seedButton");
  button.disabled = true;
  button.textContent = "Loading cafe data";
  try {
    await fetchJson("/api/data/seed", { method: "POST" });
    await refreshDashboard();
  } finally {
    button.disabled = false;
    button.textContent = "Load cafe data";
  }
});

document.getElementById("managerForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = document.getElementById("managerQuestion").value.trim();
  const answer = document.getElementById("managerAnswer");
  if (!question) {
    answer.textContent = "Ask a decision question first.";
    return;
  }
  answer.textContent = "Thinking like the cafe manager...";
  try {
    const payload = await fetchJson("/api/manager/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      timeoutMs: 12000,
    });
    answer.textContent = payload.answer;
  } catch (error) {
    answer.textContent = String(error);
  }
});

document.getElementById("uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const result = document.getElementById("uploadResult");
  const files = document.getElementById("pdfFiles").files;
  if (!files.length) {
    result.textContent = "Select at least one PDF first.";
    return;
  }

  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const batchName = document.getElementById("batchName").value.trim();
  const query = batchName ? `?batch_name=${encodeURIComponent(batchName)}` : "";

  result.textContent = "Processing receipts...";
  try {
    const payload = await fetchJson(`/api/receipts/ingest${query}`, {
      method: "POST",
      body: formData,
    });
    result.textContent = JSON.stringify(payload, null, 2);
    await refreshDashboard();
  } catch (error) {
    result.textContent = String(error);
  }
});

refreshDashboard().catch((error) => {
  document.getElementById("heroHealth").textContent = `Offline`;
  document.getElementById("managerAnswer").textContent = String(error);
});
