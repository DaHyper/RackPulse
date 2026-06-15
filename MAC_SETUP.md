# RackPulse — Mac setup guide

Step-by-step instructions to run RackPulse on macOS from the terminal.

---

## What you need first

| Requirement | Notes |
|-------------|--------|
| **macOS** | Any recent version (Ventura, Sonoma, Sequoia, etc.) |
| **Python 3.11+** | Check with `python3 --version` |
| **Network access to your gear** | Your Mac must reach PDU/NAS IPs (UDP 161), BMC/PVE IPs (HTTPS), and GPU hosts if monitored remotely |
| **Device details** | IPs, SNMP communities, BMC credentials, PVE API token — see `config.example.yaml` |

Optional but recommended:

```bash
brew install net-snmp
```

Gives you `snmpwalk` / `snmpget` to verify PDU and NAS SNMP before starting RackPulse.

For local GPU monitoring:

```bash
# NVIDIA drivers + nvidia-smi (if monitoring a Mac isn't applicable, skip — use SSH to a Linux GPU box instead)
```

---

## Step 1 — Open the project folder

If you already cloned the repo:

```bash
cd ~/Documents/GitHub/RackPulse
```

If you haven't cloned it yet:

```bash
cd ~/Documents/GitHub
git clone <your-repo-url> RackPulse
cd RackPulse
```

---

## Step 2 — Check Python

```bash
python3 --version
```

You should see **3.11** or newer. If Python is missing or too old:

```bash
brew install python@3.12
```

---

## Step 3 — Create a virtual environment

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your shell prompt should show `(.venv)`. Run `source .venv/bin/activate` again each time you open a new terminal tab.

---

## Step 4 — Install RackPulse

```bash
pip install --upgrade pip
pip install -e .
```

This installs the `rackpulse` CLI command.

Optional — if you want the HTTP API later:

```bash
pip install -e ".[api]"
```

---

## Step 5 — Create your config file

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your real values. At minimum, update:

1. **PDU IPs and community strings** under `racks` → `devices` (type `pdu`)
2. **Server BMC credentials** for `hp_server`, `dell_server`, etc.
3. **PVE token** for `pve` devices
4. **NAS community** for `nas` devices

Example snippet:

```yaml
racks:
  - name: rack-1
    location: datacenter row 1
    warning_kw: 4.0
    critical_kw: 5.0
    devices:
      - name: pdu-1
        type: pdu
        host: 192.168.1.10      # ← your PDU IP
        community: public       # ← your SNMP community

      - name: hp-server
        type: hp_server
        host: 192.168.1.20
        username: bmc-user
        password: changeme
        verify_ssl: false

      - name: pve-1
        type: pve
        host: 192.168.1.30
        token_id: monitor@pam!rackpulse
        token_secret: changeme
        verify_ssl: false
```

> `config.yaml` is git-ignored — it won't be committed. Keep SNMP communities, BMC passwords, and API tokens here only.

---

## Step 6 — Verify connectivity (strongly recommended)

Test each layer before running a full poll.

### PDU (SNMP)

```bash
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.4.1.318.1.1.26.4.3.1.5
```

Replace `public` and the IP with your community string and PDU IP. Use the raw value to confirm `pdu.power_divisor` in config:

| If raw value looks like… | Set `power_divisor` to… | Example |
|--------------------------|-------------------------|---------|
| Hundredths of kW (common on APC) | `100` | 141 → 1.41 kW |
| Watts (e.g. `1410`) | `1000` | 1410 → 1.41 kW |

### Server BMC (Redfish)

```bash
curl -sk -u bmc-user:changeme https://192.168.1.20/redfish/v1/Chassis/1/Power
```

You should get JSON with `PowerControl` or `PowerSupplies`. If the path 404s, try `/redfish/v1/Chassis/System.Embedded.1/Power` (common on Dell).

### PVE

```bash
curl -sk -H "Authorization: PVEAPIToken=monitor@pam!rackpulse=changeme" \
  https://192.168.1.30:8006/api2/json/nodes
```

### NAS (SNMP)

```bash
snmpwalk -v2c -c public 192.168.1.40 1.3.6.1.4.1.2021.4.5.0
```

If SNMP or curl times out, fix network/firewall/VPN access before continuing.

---

## Step 7 — List and test devices

Make sure the virtual environment is active (`source .venv/bin/activate`), then:

```bash
rackpulse list
rackpulse test pdu-1
rackpulse test hp-server
rackpulse test pve-1
```

Each test prints status, power, and any error for that device.

---

## Step 8 — Run RackPulse

**One-shot poll** (poll once, print dashboard, exit):

```bash
rackpulse poll
```

**Live dashboard** (refreshes every `poll_interval_seconds`):

```bash
rackpulse watch
```

Press **Ctrl+C** to stop.

**JSON output** (for scripting):

```bash
rackpulse poll --json
```

History is saved automatically to `./data/rackpulse.db`.

---

## Quick reference — every time you start it

```bash
cd ~/Documents/GitHub/RackPulse
source .venv/bin/activate
rackpulse watch
```

Or a single poll:

```bash
rackpulse poll
```

---

## Troubleshooting

### `python3: command not found`

```bash
brew install python@3.12
```

### `rackpulse: command not found`

Activate the venv and reinstall:

```bash
source .venv/bin/activate
pip install -e .
```

### Devices show as unreachable

- Confirm you can `ping` the device IP from your Mac
- Re-run the SNMP/curl checks from Step 6
- Check credentials and community strings in `config.yaml`
- Make sure UDP 161 (SNMP) and HTTPS (443/8006) aren't blocked by firewall or VPN
- For BMCs, ensure `verify_ssl: false` if using self-signed certs

### PDU power readings look wrong

Adjust `pdu.power_divisor` in `config.yaml` until values match what you expect. Re-run the `snmpwalk` from Step 6 and do the math manually.

### PVE test fails with SSL error

Set `verify_ssl: false` on the PVE device in config.

### GPU device fails on Mac

`nvidia-smi` is typically unavailable on Mac. Either:

- Point the `gpu` device at a remote Linux host via SSH (`host` + `ssh_user`), or
- Remove the GPU device from config if not needed on this machine

### `Permission denied` on SSH GPU host

Set up key-based SSH to the remote GPU box:

```bash
ssh-copy-id your-user@192.168.1.50
```

---

## Optional — HTTP API on Mac

If you installed the API extras:

```bash
pip install -e ".[api]"
rackpulse serve
```

Open http://127.0.0.1:8080/api/health

---

## Optional — Docker on Mac

```bash
cp config.example.yaml config.yaml
# edit config.yaml first

docker compose --profile watch run --rm rackpulse-watch
```

---

## Next steps

- Tune `warning_kw` / `critical_kw` per rack in `config.yaml`
- Run `rackpulse watch` in a dedicated terminal or tmux session for continuous monitoring
- Deploy to a small Linux VM in your network for 24/7 polling — see `LINUX_SETUP.md`
