const RACK_COLORS = ["#3dd68c", "#4da6ff", "#f5a623", "#c084fc", "#f472b6"];

const SNMP_TYPES = new Set(["pdu", "nas", "arista_switch", "cisco_switch", "dell_switch"]);
const BMC_TYPES = new Set(["hp_server", "dell_server", "lenovo_server"]);
const PVE_TYPES = new Set(["pve"]);
const GPU_TYPES = new Set(["gpu"]);

let config = null;
let recipients = [];
let deviceRows = [];
let deviceTypes = ["pdu", "hp_server", "dell_server", "pve", "nas", "gpu", "arista_switch"];

function alertsConfig() {
  if (!config.alerts) config.alerts = { smtp: {}, webhooks: [] };
  if (!config.alerts.smtp) config.alerts.smtp = {};
  return config.alerts;
}

async function loadConfig() {
  const typesRes = await fetch("/api/meta/device-types");
  if (typesRes.ok) {
    const meta = await typesRes.json();
    deviceTypes = meta.types || deviceTypes;
  }
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("Failed to load config");
  config = await res.json();
  if (!config.pdu) config.pdu = {};
  recipients = [...(alertsConfig().smtp.recipients || [])];
  buildDeviceRows();
  render();
}

function buildDeviceRows() {
  deviceRows = [];
  (config.racks || []).forEach((rack, rackIdx) => {
    (rack.devices || rack.pdus || []).forEach((device) => {
      deviceRows.push({
        rackIdx,
        rackName: rack.name,
        warningKw: rack.warning_kw,
        criticalKw: rack.critical_kw,
        type: device.type || "pdu",
        name: device.name || "",
        host: device.host || "",
        community: device.community || "public",
        username: device.username || "",
        password: "",
        token_id: device.token_id || "",
        token_secret: "",
        ssh_user: device.ssh_user || "",
        parent: device.parent || "",
        verify_ssl: !!device.verify_ssl,
        collect_gpu_power: !!device.collect_gpu_power,
        testStatus: "pending",
        testError: null,
      });
    });
  });
}

function typeFields(type) {
  if (SNMP_TYPES.has(type)) {
    return `
      <label class="device-field-community">
        Community
        <input type="text" class="device-community" value="">
      </label>`;
  }
  if (BMC_TYPES.has(type)) {
    return `
      <label class="device-field-user">
        Username
        <input type="text" class="device-username" value="">
      </label>
      <label class="device-field-pass">
        Password
        <input type="password" class="device-password" placeholder="Leave blank to keep stored secret">
      </label>
      <label class="checkbox-row device-field-ssl">
        <input type="checkbox" class="device-verify-ssl"> verify_ssl
      </label>`;
  }
  if (PVE_TYPES.has(type)) {
    return `
      <label class="device-field-token-id">
        Token ID
        <input type="text" class="device-token-id" value="">
      </label>
      <label class="device-field-token-secret">
        Token secret
        <input type="password" class="device-token-secret" placeholder="Leave blank to keep stored secret">
      </label>
      <label class="device-field-parent">
        Parent device
        <input type="text" class="device-parent" placeholder="optional BMC host name">
      </label>
      <label class="checkbox-row device-field-gpu">
        <input type="checkbox" class="device-collect-gpu"> collect_gpu_power
      </label>
      <label class="device-field-ssh">
        SSH user
        <input type="text" class="device-ssh-user" placeholder="for GPU power">
      </label>
      <label class="checkbox-row device-field-ssl">
        <input type="checkbox" class="device-verify-ssl"> verify_ssl
      </label>`;
  }
  if (GPU_TYPES.has(type)) {
    return `
      <label class="device-field-ssh">
        SSH user
        <input type="text" class="device-ssh-user" placeholder="optional for remote host">
      </label>`;
  }
  return "";
}

function renderDeviceTable() {
  const tbody = document.getElementById("pdu-tbody");
  tbody.innerHTML = deviceRows
    .map((row, i) => {
      const color = RACK_COLORS[row.rackIdx % RACK_COLORS.length];
      const statusCls =
        row.testStatus === "ok" ? "ok" : row.testStatus === "fail" ? "fail" : "pending";
      const statusLabel =
        row.testStatus === "ok" ? "✓ OK" : row.testStatus === "fail" ? "✗ Fail" : "—";
      const typeOptions = deviceTypes
        .map(
          (t) =>
            `<option value="${t}" ${t === row.type ? "selected" : ""}>${t}</option>`
        )
        .join("");
      return `
        <tr data-row="${i}" class="device-row">
          <td><span class="rack-dot" style="background:${color}"></span></td>
          <td><input type="text" class="device-name" value="${esc(row.name)}"></td>
          <td>
            <select class="device-type">${typeOptions}</select>
          </td>
          <td>
            <select class="device-rack">
              ${(config.racks || [])
                .map(
                  (r, ri) =>
                    `<option value="${ri}" ${ri === row.rackIdx ? "selected" : ""}>${esc(r.name)}</option>`
                )
                .join("")}
            </select>
          </td>
          <td><input type="text" class="device-host" value="${esc(row.host)}"></td>
          <td class="device-extra-fields">${typeFields(row.type)}</td>
          <td><span class="conn-status ${statusCls}">${statusLabel}</span></td>
          <td><button class="btn btn-danger btn-sm remove-device" type="button">✕</button></td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll(".device-row").forEach((tr) => {
    const idx = parseInt(tr.dataset.row, 10);
    const row = deviceRows[idx];
    if (!row) return;
    const type = tr.querySelector(".device-type").value;
    if (SNMP_TYPES.has(type) && tr.querySelector(".device-community")) {
      tr.querySelector(".device-community").value = row.community || "public";
    }
    if (BMC_TYPES.has(type)) {
      if (tr.querySelector(".device-username")) tr.querySelector(".device-username").value = row.username || "";
      if (tr.querySelector(".device-verify-ssl")) tr.querySelector(".device-verify-ssl").checked = row.verify_ssl;
    }
    if (PVE_TYPES.has(type)) {
      if (tr.querySelector(".device-token-id")) tr.querySelector(".device-token-id").value = row.token_id || "";
      if (tr.querySelector(".device-parent")) tr.querySelector(".device-parent").value = row.parent || "";
      if (tr.querySelector(".device-ssh-user")) tr.querySelector(".device-ssh-user").value = row.ssh_user || "";
      if (tr.querySelector(".device-collect-gpu")) tr.querySelector(".device-collect-gpu").checked = row.collect_gpu_power;
      if (tr.querySelector(".device-verify-ssl")) tr.querySelector(".device-verify-ssl").checked = row.verify_ssl;
    }
    if (GPU_TYPES.has(type) && tr.querySelector(".device-ssh-user")) {
      tr.querySelector(".device-ssh-user").value = row.ssh_user || "";
    }
  });

  tbody.querySelectorAll(".device-type").forEach((sel) => {
    sel.addEventListener("change", () => {
      const tr = sel.closest("tr");
      const idx = parseInt(tr.dataset.row, 10);
      deviceRows[idx].type = sel.value;
      tr.querySelector(".device-extra-fields").innerHTML = typeFields(sel.value);
      renderDeviceTable();
    });
  });

  tbody.querySelectorAll(".remove-device").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.closest("tr").dataset.row, 10);
      deviceRows.splice(idx, 1);
      syncRowsToConfig();
      buildDeviceRows();
      renderDeviceTable();
      renderThresholds();
    });
  });
}

function renderThresholds() {
  const grid = document.getElementById("threshold-grid");
  grid.innerHTML = (config.racks || [])
    .map(
      (rack, i) => `
      <div class="threshold-rack" data-rack="${i}">
        <div class="form-row">
          <label>
            Rack name
            <input type="text" class="rack-name" value="${esc(rack.name)}" placeholder="rack-1">
          </label>
          <label>
            Location
            <input type="text" class="rack-description" value="${esc(rack.location ?? rack.description ?? "")}" placeholder="datacenter row 1">
          </label>
        </div>
        <div class="form-row">
          <label>
            Warning threshold (kW)
            <input type="number" class="rack-warning" step="0.01" value="${rack.warning_kw ?? ""}">
          </label>
          <label>
            Critical threshold (kW)
            <input type="number" class="rack-critical" step="0.01" value="${rack.critical_kw ?? ""}">
          </label>
        </div>
      </div>`
    )
    .join("");
}

function renderRecipients() {
  const wrap = document.getElementById("recipients-wrap");
  wrap.innerHTML = recipients
    .map(
      (email, i) => `
      <span class="recipient-chip">
        ${esc(email)}
        <button type="button" data-idx="${i}" class="remove-recipient">×</button>
      </span>`
    )
    .join("");

  wrap.querySelectorAll(".remove-recipient").forEach((btn) => {
    btn.addEventListener("click", () => {
      recipients.splice(parseInt(btn.dataset.idx, 10), 1);
      renderRecipients();
    });
  });
}

function renderWebhooks() {
  const alerts = alertsConfig();
  if (!alerts.webhooks) alerts.webhooks = [];
  const list = document.getElementById("webhook-list");
  if (!alerts.webhooks.length) {
    list.innerHTML =
      '<p class="hint">No webhooks configured. Add one for Slack, Discord, or a custom endpoint.</p>';
    return;
  }
  list.innerHTML = alerts.webhooks
    .map(
      (wh, i) => `
      <div class="webhook-item" data-webhook="${i}">
        <div class="webhook-item-header">
          <label>
            <input type="checkbox" class="webhook-enabled" ${wh.enabled !== false ? "checked" : ""}>
            Enabled
          </label>
          <button class="btn btn-danger btn-sm remove-webhook" type="button">Remove</button>
        </div>
        <div class="form-stack">
          <label>
            Name
            <input type="text" class="webhook-name" value="${esc(wh.name || "")}">
          </label>
          <label>
            Webhook URL
            <input type="url" class="webhook-url" value="${esc(wh.url || "")}">
          </label>
          <label>
            Format
            <select class="webhook-format">
              <option value="generic" ${wh.format === "generic" ? "selected" : ""}>Generic JSON</option>
              <option value="slack" ${wh.format === "slack" ? "selected" : ""}>Slack</option>
              <option value="discord" ${wh.format === "discord" ? "selected" : ""}>Discord</option>
            </select>
          </label>
        </div>
      </div>`
    )
    .join("");

  list.querySelectorAll(".remove-webhook").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.closest(".webhook-item").dataset.webhook, 10);
      alerts.webhooks.splice(idx, 1);
      renderWebhooks();
    });
  });
}

function syncWebhooksFromForm() {
  const alerts = alertsConfig();
  alerts.webhooks = [];
  document.querySelectorAll(".webhook-item").forEach((el) => {
    alerts.webhooks.push({
      name: el.querySelector(".webhook-name").value.trim(),
      url: el.querySelector(".webhook-url").value.trim(),
      format: el.querySelector(".webhook-format").value,
      enabled: el.querySelector(".webhook-enabled").checked,
    });
  });
}

function toggleSnmpV3Panel() {
  const version = document.getElementById("snmp-version").value;
  document.getElementById("snmp-v3-panel").hidden = version !== "3";
}

function isoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function renderMaintenance() {
  const m = config.maintenance || {};
  document.getElementById("maintenance-enabled").checked = !!m.enabled;
  document.getElementById("maintenance-silence").checked = m.silence_alerts !== false;
  document.getElementById("maintenance-message").value = m.message || "";
  document.getElementById("maintenance-until").value = isoToLocalInput(m.until);
}

function syncMaintenanceFromForm() {
  if (!config.maintenance) config.maintenance = {};
  config.maintenance.enabled = document.getElementById("maintenance-enabled").checked;
  config.maintenance.silence_alerts = document.getElementById("maintenance-silence").checked;
  config.maintenance.message = document.getElementById("maintenance-message").value;
  config.maintenance.until = localInputToIso(document.getElementById("maintenance-until").value) || null;
}

function renderAuthAndServer() {
  const auth = config.auth || {};
  const server = config.server || {};
  document.getElementById("auth-enabled").checked = !!auth.enabled;
  document.getElementById("auth-api-key").value = "";
  document.getElementById("server-host").value = server.host || "127.0.0.1";
  document.getElementById("server-port").value = server.port || 8080;
}

function syncAuthAndServerFromForm() {
  if (!config.auth) config.auth = {};
  if (!config.server) config.server = {};
  config.auth.enabled = document.getElementById("auth-enabled").checked;
  const apiKey = document.getElementById("auth-api-key").value;
  if (apiKey) config.auth.api_key = apiKey;
  config.server.host = document.getElementById("server-host").value.trim() || "127.0.0.1";
  config.server.port = parseInt(document.getElementById("server-port").value, 10) || 8080;
}

function renderSnmp() {
  const snmp = config.snmp || {};
  const v3 = snmp.v3 || {};
  document.getElementById("snmp-version").value = snmp.version || "2c";
  document.getElementById("v3-username").value = v3.username || "";
  document.getElementById("v3-security-level").value = v3.security_level || "authPriv";
  document.getElementById("v3-auth-password").value = "";
  document.getElementById("v3-auth-protocol").value = v3.auth_protocol || "SHA";
  document.getElementById("v3-priv-password").value = "";
  document.getElementById("v3-priv-protocol").value = v3.priv_protocol || "AES";
  toggleSnmpV3Panel();
}

function syncSnmpFromForm() {
  if (!config.snmp) config.snmp = {};
  config.snmp.version = document.getElementById("snmp-version").value;
  if (!config.snmp.v3) config.snmp.v3 = {};
  config.snmp.v3.username = document.getElementById("v3-username").value;
  config.snmp.v3.security_level = document.getElementById("v3-security-level").value;
  config.snmp.v3.auth_protocol = document.getElementById("v3-auth-protocol").value;
  config.snmp.v3.priv_protocol = document.getElementById("v3-priv-protocol").value;
  const authPw = document.getElementById("v3-auth-password").value;
  const privPw = document.getElementById("v3-priv-password").value;
  if (authPw) config.snmp.v3.auth_password = authPw;
  if (privPw) config.snmp.v3.priv_password = privPw;
}

function render() {
  const pdu = config.pdu || {};
  const alerts = alertsConfig();
  document.getElementById("poll-interval").value = config.poll_interval_seconds;
  document.getElementById("alert-cooldown").value = alerts.cooldown_minutes ?? 15;
  document.getElementById("power-oid").value = pdu.power_oid || "";
  document.getElementById("power-divisor").value = pdu.power_divisor ?? 100;
  document.getElementById("energy-oid").value = pdu.energy_oid || "";
  document.getElementById("energy-divisor").value = pdu.energy_divisor ?? 10;

  renderSnmp();
  renderAuthAndServer();
  renderMaintenance();

  document.getElementById("smtp-host").value = alerts.smtp.host || "";
  document.getElementById("smtp-port").value = alerts.smtp.port || 587;
  document.getElementById("smtp-security").value = alerts.smtp.security || "tls";
  document.getElementById("smtp-username").value = alerts.smtp.username || "";
  document.getElementById("smtp-password").value = "";
  document.getElementById("smtp-from").value = alerts.smtp.from_address || "";

  renderDeviceTable();
  renderThresholds();
  renderWebhooks();
  renderRecipients();
}

function deviceFromRow(row, tr) {
  const type = tr.querySelector(".device-type").value;
  const device = {
    name: tr.querySelector(".device-name").value.trim(),
    type,
    host: tr.querySelector(".device-host").value.trim(),
  };
  if (SNMP_TYPES.has(type)) {
    device.community = tr.querySelector(".device-community")?.value.trim() || "public";
  }
  if (BMC_TYPES.has(type)) {
    device.username = tr.querySelector(".device-username")?.value.trim() || "";
    const pw = tr.querySelector(".device-password")?.value;
    if (pw) device.password = pw;
    if (tr.querySelector(".device-verify-ssl")?.checked) device.verify_ssl = true;
  }
  if (PVE_TYPES.has(type)) {
    device.token_id = tr.querySelector(".device-token-id")?.value.trim() || "";
    const secret = tr.querySelector(".device-token-secret")?.value;
    if (secret) device.token_secret = secret;
    const parent = tr.querySelector(".device-parent")?.value.trim();
    if (parent) device.parent = parent;
    const ssh = tr.querySelector(".device-ssh-user")?.value.trim();
    if (ssh) device.ssh_user = ssh;
    if (tr.querySelector(".device-collect-gpu")?.checked) device.collect_gpu_power = true;
    if (tr.querySelector(".device-verify-ssl")?.checked) device.verify_ssl = true;
  }
  if (GPU_TYPES.has(type)) {
    const ssh = tr.querySelector(".device-ssh-user")?.value.trim();
    if (ssh) device.ssh_user = ssh;
  }
  return device;
}

function syncRowsToConfig() {
  const racks = (config.racks || []).map((r) => ({
    name: r.name,
    location: r.location ?? r.description ?? "",
    warning_kw: r.warning_kw,
    critical_kw: r.critical_kw,
    devices: [],
  }));

  const tbody = document.getElementById("pdu-tbody");
  tbody.querySelectorAll("tr").forEach((tr) => {
    const idx = parseInt(tr.dataset.row, 10);
    const row = deviceRows[idx];
    if (!row) return;
    const rackIdx = parseInt(tr.querySelector(".device-rack").value, 10);
    if (!racks[rackIdx]) return;
    racks[rackIdx].devices.push(deviceFromRow(row, tr));
  });

  config.racks = racks;
}

function syncRowsFromTable() {
  const tbody = document.getElementById("pdu-tbody");
  tbody.querySelectorAll("tr").forEach((tr) => {
    const idx = parseInt(tr.dataset.row, 10);
    const row = deviceRows[idx];
    if (!row) return;
    row.name = tr.querySelector(".device-name").value;
    row.rackIdx = parseInt(tr.querySelector(".device-rack").value, 10);
    row.type = tr.querySelector(".device-type").value;
    row.host = tr.querySelector(".device-host").value;
  });
  syncRowsToConfig();
}

function syncThresholdsFromForm() {
  document.querySelectorAll(".threshold-rack").forEach((el) => {
    const idx = parseInt(el.dataset.rack, 10);
    config.racks[idx].name = el.querySelector(".rack-name").value.trim() || `rack-${idx + 1}`;
    config.racks[idx].location = el.querySelector(".rack-description").value;
    config.racks[idx].warning_kw = parseFloat(el.querySelector(".rack-warning").value);
    config.racks[idx].critical_kw = parseFloat(el.querySelector(".rack-critical").value);
  });
}

function readFormIntoConfig() {
  syncRowsFromTable();
  syncThresholdsFromForm();
  syncWebhooksFromForm();
  syncAuthAndServerFromForm();
  syncMaintenanceFromForm();
  syncSnmpFromForm();

  const alerts = alertsConfig();
  config.poll_interval_seconds = parseInt(document.getElementById("poll-interval").value, 10);
  alerts.cooldown_minutes = parseInt(document.getElementById("alert-cooldown").value, 10);

  if (!config.pdu) config.pdu = {};
  config.pdu.power_oid = document.getElementById("power-oid").value;
  config.pdu.power_divisor = parseFloat(document.getElementById("power-divisor").value);
  config.pdu.energy_oid = document.getElementById("energy-oid").value;
  config.pdu.energy_divisor = parseFloat(document.getElementById("energy-divisor").value);

  alerts.smtp.host = document.getElementById("smtp-host").value;
  alerts.smtp.port = parseInt(document.getElementById("smtp-port").value, 10);
  alerts.smtp.security = document.getElementById("smtp-security").value;
  alerts.smtp.username = document.getElementById("smtp-username").value;
  const pw = document.getElementById("smtp-password").value;
  if (pw) alerts.smtp.password = pw;
  alerts.smtp.from_address = document.getElementById("smtp-from").value;
  alerts.smtp.recipients = [...recipients];
}

function showStatus(msg, ok) {
  const el = document.getElementById("save-status");
  el.textContent = msg;
  el.className = `save-status ${ok ? "success" : "error"}`;
  el.hidden = false;
  setTimeout(() => {
    el.hidden = true;
  }, 4000);
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str ?? "";
  return d.innerHTML;
}

document.getElementById("save-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  const res = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const data = await res.json();
  if (res.ok) {
    config = data.config;
    buildDeviceRows();
    render();
    showStatus("Configuration saved. Secrets stored outside config.yaml.", true);
  } else {
    showStatus(data.detail || "Save failed.", false);
  }
});

document.getElementById("test-all-btn").addEventListener("click", async () => {
  syncRowsFromTable();
  readFormIntoConfig();
  const btn = document.getElementById("test-all-btn");
  btn.disabled = true;
  deviceRows.forEach((r) => {
    r.testStatus = "pending";
  });
  renderDeviceTable();

  const res = await fetch("/api/test/devices/all", { method: "POST" });
  const data = await res.json();

  (data.results || []).forEach((result) => {
    const row = deviceRows.find((r) => r.host === result.host && r.name === result.name);
    if (row) {
      row.testStatus = result.ok ? "ok" : "fail";
      row.testError = result.error;
    }
  });
  renderDeviceTable();
  btn.disabled = false;
});

document.getElementById("add-rack-btn").addEventListener("click", () => {
  syncRowsFromTable();
  syncThresholdsFromForm();
  config.racks.push({
    name: `rack-${config.racks.length + 1}`,
    location: "",
    warning_kw: 4.0,
    critical_kw: 5.0,
    devices: [],
  });
  buildDeviceRows();
  renderDeviceTable();
  renderThresholds();
});

document.getElementById("add-pdu-btn").addEventListener("click", () => {
  syncRowsFromTable();
  syncThresholdsFromForm();
  if (!config.racks.length) {
    config.racks.push({
      name: "rack-1",
      location: "",
      warning_kw: 4.0,
      critical_kw: 5.0,
      devices: [],
    });
  }
  deviceRows.push({
    rackIdx: 0,
    type: "pdu",
    name: `pdu-${deviceRows.length + 1}`,
    host: "192.168.1.10",
    community: "public",
    testStatus: "pending",
  });
  syncRowsToConfig();
  buildDeviceRows();
  renderDeviceTable();
  renderThresholds();
});

document.getElementById("add-recipient-btn").addEventListener("click", () => {
  const input = document.getElementById("recipient-input");
  const email = input.value.trim();
  if (email && !recipients.includes(email)) {
    recipients.push(email);
    renderRecipients();
  }
  input.value = "";
});

document.getElementById("add-webhook-btn").addEventListener("click", () => {
  syncWebhooksFromForm();
  const alerts = alertsConfig();
  alerts.webhooks.push({ name: "", url: "", format: "slack", enabled: true });
  renderWebhooks();
});

document.getElementById("test-webhooks-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const res = await fetch("/api/test/webhooks", { method: "POST" });
  const data = await res.json();
  showStatus(res.ok ? "Test webhook sent." : data.detail || "Webhook test failed.", res.ok);
});

document.getElementById("snmp-version").addEventListener("change", toggleSnmpV3Panel);

document.getElementById("export-config-btn").addEventListener("click", () => {
  window.location.href = "/api/config/export";
});

document.getElementById("import-config-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/config/import", { method: "POST", body: form });
  const data = await res.json();
  if (res.ok) {
    config = data.config;
    buildDeviceRows();
    render();
    showStatus("Configuration imported.", true);
  } else {
    showStatus(data.detail || "Import failed.", false);
  }
  e.target.value = "";
});

document.getElementById("test-smtp-btn").addEventListener("click", async () => {
  readFormIntoConfig();
  await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  const res = await fetch("/api/test/smtp", { method: "POST" });
  const data = await res.json();
  showStatus(res.ok ? "Test email sent." : data.detail || "SMTP test failed.", res.ok);
});

loadConfig().catch((err) => showStatus(err.message, false));
