const STATUS_LABELS = {
  ok: "Normal",
  warning: "Warning",
  low: "Warning",
  critical: "Danger",
  unknown: "Unknown",
};

let pollTimer = null;
let activeView = "racks";
let lastData = null;

async function fetchStatus() {
  const res = await fetch("/api/status?view=dashboard");
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

function formatKw(value) {
  if (value == null) return "—";
  return Number(value).toFixed(2);
}

function formatWatts(watts) {
  if (watts == null) return "—";
  if (watts >= 1000) return `${(watts / 1000).toFixed(2)} kW`;
  return `${Math.round(watts)} W`;
}

function formatPct(value) {
  if (value == null) return "—";
  return `${Math.round(value)}%`;
}

function statusClass(status) {
  if (status === "ok") return "ok";
  if (status === "stale") return "pending";
  return "fail";
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str ?? "";
  return d.innerHTML;
}

function renderSparkline(points, warningKw, criticalKw) {
  if (!points || points.length < 2) {
    return '<div class="sparkline-wrap"><div class="sparkline-empty">Collecting 24h history…</div></div>';
  }

  const valid = points.filter((p) => p.kw != null);
  if (valid.length < 2) {
    return '<div class="sparkline-wrap"><div class="sparkline-empty">Collecting 24h history…</div></div>';
  }

  const w = 300;
  const h = 52;
  const pad = 3;
  const maxY = Math.max(criticalKw * 1.15, ...valid.map((p) => p.kw), 0.5);

  const coords = valid
    .map((p, i) => {
      const x = pad + (i / (valid.length - 1)) * (w - pad * 2);
      const y = h - pad - (p.kw / maxY) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const warnY = h - pad - (warningKw / maxY) * (h - pad * 2);
  const critY = h - pad - (criticalKw / maxY) * (h - pad * 2);

  return `
    <div class="sparkline-wrap">
      <div class="sparkline-header">
        <span>Last 24 hours</span>
        <span class="sparkline-legend">
          <span class="legend-warn">— warn</span>
          <span class="legend-crit">— limit</span>
        </span>
      </div>
      <svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
        <line x1="${pad}" y1="${warnY}" x2="${w - pad}" y2="${warnY}" class="sparkline-warn-line"/>
        <line x1="${pad}" y1="${critY}" x2="${w - pad}" y2="${critY}" class="sparkline-crit-line"/>
        <polyline points="${coords}" class="sparkline-line"/>
      </svg>
    </div>`;
}

function renderPduItem(device) {
  const cls =
    device.status === "unreachable" || device.status === "error"
      ? "unreachable"
      : device.status === "stale"
        ? "stale"
        : "";
  const power =
    device.power_kw != null
      ? `${formatKw(device.power_kw)} kW`
      : device.power_watts != null
        ? `${formatKw(device.power_watts / 1000)} kW`
        : "—";
  const err = device.error ? `<div class="pdu-error">${esc(device.error)}</div>` : "";
  return `
    <div class="pdu-item ${cls}">
      <div class="pdu-item-header">
        <span class="pdu-item-name">${esc(device.name)}</span>
        <span class="device-type">pdu</span>
      </div>
      <div class="pdu-power">${power}</div>
      <div class="pdu-host">${esc(device.host)}</div>
      ${err}
    </div>`;
}

function renderRackCard(rack, history) {
  const status = rack.status || "unknown";
  const pct = rack.percent_of_limit ?? 0;
  const barWidth = Math.min(pct, 100);
  const sparkline = renderSparkline(history, rack.warning_kw, rack.critical_kw);
  const pdus = rack.pdus || (rack.devices || []).filter((d) => d.type === "pdu");
  const pduHtml = pdus.length
    ? pdus.map(renderPduItem).join("")
    : '<div class="pdu-empty">No PDUs on this rack.</div>';

  return `
    <div class="rack-card status-${status}">
      <div class="rack-header">
        <div>
          <div class="rack-name">${esc(rack.name)}</div>
          <div class="rack-description">${esc(rack.description || rack.location || "")}</div>
        </div>
        <span class="status-badge ${status}">${STATUS_LABELS[status] || status}</span>
      </div>
      <div class="rack-power">
        <span class="power-value ${status}">${formatKw(rack.power_kw)}</span>
        <span class="power-limit"> kW / ${formatKw(rack.critical_kw)} kW limit</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill ${status}" style="width: ${barWidth}%"></div>
      </div>
      <div class="rack-meta">
        <span>${pct}% of limit</span>
        <span class="headroom ${status}">${formatKw(rack.headroom_kw)} kW headroom</span>
      </div>
      ${sparkline}
      <div class="pdu-list">${pduHtml}</div>
    </div>`;
}

function renderPollRow(device) {
  const childCls = device.parent ? "child-row" : "";
  const prefix = device.parent ? "↳ " : "";
  const temp =
    device.temperature_c != null ? `${Math.round(device.temperature_c)}°C` : "—";
  const statusText = device.error
    ? `${device.status} (${device.error.length > 36 ? device.error.slice(0, 33) + "…" : device.error})`
    : device.status;

  return `
    <tr class="${childCls}">
      <td>${prefix}${esc(device.name)}</td>
      <td>${esc(device.type)}</td>
      <td>${esc(device.host)}</td>
      <td class="num">${formatWatts(device.power_watts)}</td>
      <td class="num">${formatPct(device.cpu_percent)}</td>
      <td class="num">${formatPct(device.ram_percent)}</td>
      <td class="num">${temp}</td>
      <td><span class="conn-status ${statusClass(device.status)}">${esc(statusText)}</span></td>
    </tr>`;
}

function renderPollView(racks) {
  if (!racks.length) {
    return '<p class="loading">No racks configured. <a href="/config" style="color:var(--blue)">Add devices</a>.</p>';
  }

  return racks
    .map((rack) => {
      const devices = rack.devices || [];
      const rows = devices.map(renderPollRow).join("");
      const gap =
        rack.unaccounted_watts != null
          ? `<span>Unmetered gap: <strong>${formatWatts(rack.unaccounted_watts)}</strong></span>`
          : "";

      return `
        <section class="device-rack-panel">
          <div class="device-rack-header">
            <div>
              <div class="device-rack-title">${esc(rack.name)}${rack.location ? ` — ${esc(rack.location)}` : ""}</div>
              <div class="device-rack-location">
                <span class="status-badge ${rack.status || "unknown"}">${STATUS_LABELS[rack.status] || rack.status}</span>
                <span class="poll-rack-power">${formatWatts(rack.power_watts != null ? rack.power_watts : rack.power_kw != null ? rack.power_kw * 1000 : null)}</span>
              </div>
            </div>
            <div class="device-rack-totals">
              <span>PDU metered: <strong>${formatWatts(rack.pdu_total_watts)}</strong></span>
              <span>Devices reporting: <strong>${formatWatts(rack.measured_device_watts)}</strong></span>
              ${gap}
            </div>
          </div>
          <table class="device-table poll-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Type</th>
                <th>Host</th>
                <th>Power</th>
                <th>CPU</th>
                <th>RAM</th>
                <th>Temp</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </section>`;
    })
    .join("");
}

function renderCombinedView(racks) {
  const section = document.getElementById("combined-view");
  if (!racks.length || activeView !== "racks") {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const maxCritical = Math.max(...racks.map((r) => r.critical_kw || 0));
  const maxWarning = Math.max(...racks.map((r) => r.warning_kw || 0));
  const totalKw = racks.reduce((sum, r) => sum + (r.power_kw || 0), 0);

  const rackParts = racks
    .map((r) => `${esc(r.name)} <strong>${formatKw(r.power_kw)} kW</strong>`)
    .join(" · ");

  document.getElementById("combined-summary").innerHTML =
    `${rackParts} · Warn at <strong>${formatKw(maxWarning)} kW</strong> · Limit <span class="limit">${formatKw(maxCritical)} kW</span>`;

  const scaleMax = maxCritical * 1.2 || 1;
  const warnPct = (maxWarning / scaleMax) * 100;
  const critPct = ((maxCritical - maxWarning) / scaleMax) * 100;
  const okPct = Math.max(100 - warnPct - critPct, 0);

  const track = document.getElementById("gauge-track");
  track.querySelector(".gauge-zone-ok").style.width = `${okPct}%`;
  track.querySelector(".gauge-zone-warn").style.width = `${warnPct}%`;
  track.querySelector(".gauge-zone-critical").style.width = `${critPct}%`;

  const markerPct = (maxCritical / scaleMax) * 100;
  const marker = document.getElementById("gauge-marker");
  marker.style.left = `${markerPct}%`;
  document.getElementById("gauge-limit-label").style.left = `${markerPct}%`;
  document.getElementById("gauge-limit-label").textContent = `${formatKw(maxCritical)} kW`;

  const arrowPct = Math.min((totalKw / scaleMax) * 100, 100);
  document.getElementById("gauge-arrow").style.left = `${arrowPct}%`;
}

function updateMaintenanceBanner(data) {
  const banner = document.getElementById("maintenance-banner");
  if (!data.maintenance_enabled) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  const silence = data.alerts_silenced ? "Alerts silenced." : "Alerts active.";
  const msg = data.maintenance_message || "Maintenance mode is active.";
  banner.innerHTML = `<strong>Maintenance mode</strong> — ${esc(msg)} ${silence}`;
}

function updateHeader(racks, interval, deviceView) {
  const deviceCount = deviceView?.length
    ? deviceView.reduce((n, r) => n + (r.devices || []).length, 0)
    : racks.reduce((n, r) => n + (r.devices || r.pdus || []).length, 0);
  document.getElementById("header-subtitle").textContent =
    `${racks.length} rack${racks.length !== 1 ? "s" : ""} · ${deviceCount} device${deviceCount !== 1 ? "s" : ""}`;
  document.getElementById("poll-interval").textContent = interval;
}

function updateLastPoll(iso) {
  const el = document.getElementById("last-poll");
  if (!iso) {
    el.textContent = "Last poll: —";
    return;
  }
  const d = new Date(iso);
  el.textContent = `Last poll: ${d.toLocaleString()}`;
}

function setActiveView(view) {
  activeView = view;
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  if (!lastData) return;
  render(lastData);
}

function render(data) {
  lastData = data;
  const racks = data.racks || [];
  const rackGrid = document.getElementById("rack-grid");
  const deviceView = document.getElementById("device-view");

  if (!racks.length) {
    const empty =
      '<p class="loading">No racks configured. <a href="/config" style="color:var(--blue)">Add devices</a>.</p>';
    rackGrid.innerHTML = empty;
    deviceView.innerHTML = empty;
    rackGrid.hidden = false;
    deviceView.hidden = true;
    document.getElementById("combined-view").hidden = true;
    updateHeader([], data.poll_interval_seconds, []);
    updateLastPoll(data.last_poll);
    return;
  }

  if (activeView === "devices") {
    rackGrid.hidden = true;
    deviceView.hidden = false;
    deviceView.innerHTML = renderPollView(data.device_view || []);
    document.getElementById("combined-view").hidden = true;
  } else {
    rackGrid.hidden = false;
    deviceView.hidden = true;
    const history = data.history || {};
    rackGrid.innerHTML = racks.map((rack) => renderRackCard(rack, history[rack.name] || [])).join("");
    renderCombinedView(racks);
  }

  updateMaintenanceBanner(data);
  updateHeader(racks, data.poll_interval_seconds, data.device_view);
  updateLastPoll(data.last_poll);
  schedulePoll(data.poll_interval_seconds);
}

function schedulePoll(intervalSeconds) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const data = await fetchStatus();
      render(data);
    } catch (_) {
      /* retry next interval */
    }
  }, intervalSeconds * 1000);
}

async function init() {
  try {
    const data = await fetchStatus();
    render(data);
  } catch (err) {
    document.getElementById("rack-grid").innerHTML =
      `<p class="loading">Error loading data: ${esc(err.message)}</p>`;
  }
}

document.getElementById("tab-racks").addEventListener("click", () => setActiveView("racks"));
document.getElementById("tab-devices").addEventListener("click", () => setActiveView("devices"));

document.getElementById("refresh-btn").addEventListener("click", async () => {
  const btn = document.getElementById("refresh-btn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/refresh?view=dashboard", { method: "POST" });
    const data = await res.json();
    render(data);
  } finally {
    btn.disabled = false;
  }
});

init();
