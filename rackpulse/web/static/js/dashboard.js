const STATUS_LABELS = {
  ok: "Normal",
  warning: "Warning",
  low: "Warning",
  critical: "Danger",
  unknown: "Unknown",
};

let pollTimer = null;

async function fetchStatus() {
  const res = await fetch("/api/status?view=dashboard");
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

function formatKw(value) {
  if (value == null) return "—";
  return Number(value).toFixed(2);
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

function renderDeviceItem(device) {
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
  const err = device.error ? `<div class="pdu-error">${device.error}</div>` : "";
  const typeLabel = device.type ? `<span class="device-type">${device.type}</span>` : "";
  return `
    <div class="pdu-item ${cls}">
      <div class="pdu-item-header">
        <span class="pdu-item-name">${device.name}</span>
        ${typeLabel}
      </div>
      <div class="pdu-power">${power}</div>
      <div class="pdu-host">${device.host}</div>
      ${err}
    </div>`;
}

function renderRackCard(rack, history) {
  const status = rack.status || "unknown";
  const pct = rack.percent_of_limit ?? 0;
  const barWidth = Math.min(pct, 100);
  const sparkline = renderSparkline(history, rack.warning_kw, rack.critical_kw);
  const devices = rack.devices || rack.pdus || [];
  const deviceHtml = devices.map(renderDeviceItem).join("");

  return `
    <div class="rack-card status-${status}">
      <div class="rack-header">
        <div>
          <div class="rack-name">${rack.name}</div>
          <div class="rack-description">${rack.description || rack.location || ""}</div>
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
      <div class="pdu-list">${deviceHtml}</div>
    </div>`;
}

function renderCombinedView(racks) {
  const section = document.getElementById("combined-view");
  if (!racks.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const maxCritical = Math.max(...racks.map((r) => r.critical_kw || 0));
  const maxWarning = Math.max(...racks.map((r) => r.warning_kw || 0));
  const totalKw = racks.reduce((sum, r) => sum + (r.power_kw || 0), 0);

  const rackParts = racks
    .map((r) => `${r.name} <strong>${formatKw(r.power_kw)} kW</strong>`)
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
  banner.innerHTML = `<strong>Maintenance mode</strong> — ${msg} ${silence}`;
}

function updateHeader(racks, interval) {
  const deviceCount = racks.reduce(
    (n, r) => n + (r.devices || r.pdus || []).length,
    0
  );
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

function render(data) {
  const grid = document.getElementById("rack-grid");
  if (!data.racks || !data.racks.length) {
    grid.innerHTML =
      '<p class="loading">No racks configured. <a href="/config" style="color:var(--blue)">Add devices</a>.</p>';
    return;
  }
  const history = data.history || {};
  grid.innerHTML = data.racks
    .map((rack) => renderRackCard(rack, history[rack.name] || []))
    .join("");
  renderCombinedView(data.racks);
  updateMaintenanceBanner(data);
  updateHeader(data.racks, data.poll_interval_seconds);
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
      `<p class="loading">Error loading data: ${err.message}</p>`;
  }
}

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
