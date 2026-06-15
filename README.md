# RackPulse

Multi-rack power and infrastructure monitoring for PDUs, HP/Dell/Lenovo servers, PVE nodes, NAS, and GPU hosts. Stores history locally and shows a live terminal dashboard.

Evolved from [PDU-Power-Monitor](https://github.com/DaHyper/PDU-Power-Monitor) with support for full rack inventory beyond PDUs.

**Setup guides:** [Mac](MAC_SETUP.md) · [Linux (CLI)](LINUX_SETUP.md)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp config.example.yaml config.yaml
# Edit config.yaml with your rack IPs and credentials

rackpulse list          # show configured devices
rackpulse test pdu-1    # test one device
rackpulse poll          # one-shot poll + dashboard
rackpulse watch         # live terminal dashboard
```

## Device types

| Type | What it covers | Metrics |
|------|----------------|---------|
| `pdu` | Rack PDU (SNMP) | Power (W), energy (kWh) |
| `hp_server` | HP server BMC (iLO / Redfish) | Power (W), temperature |
| `dell_server` | Dell server BMC (iDRAC / Redfish) | Power (W), temperature |
| `lenovo_server` | Lenovo server BMC (XCC / Redfish) | Power (W), temperature |
| `pve` | Proxmox VE node | CPU/RAM, VM inventory |
| `nas` | NAS appliance (SNMP) | CPU, RAM, temperature |
| `gpu` | GPU workstation (nvidia-smi) | GPU power, utilization, temperature |

Device **names** are yours (`hp-server`, `pve-1`, `nas-1`, etc.). Types pick the collector — no model numbers needed.

### Where power readings come from

| Source | Power? | Notes |
|--------|--------|-------|
| `pdu` | Rack total | One number for the whole PDU — not per-outlet unless your hardware supports branch metering |
| `hp_server` / `dell_server` / `lenovo_server` | Per server | BMC reports chassis power (W) |
| `pve` | No (CPU/RAM only) | Unless `collect_gpu_power: true` — then GPU draw via `nvidia-smi` over SSH |
| `gpu` | Per host | Sum of GPU power draw (local or SSH) |
| `nas` | No | Synology SNMP has temp/CPU/RAM but not system watts |

For GPU hosts, add `collect_gpu_power: true` and `ssh_user` on the PVE entry, or use a separate `gpu` device:

```yaml
- name: gpu-host-1
  type: pve
  host: 192.168.1.50
  collect_gpu_power: true
  ssh_user: root
  token_id: monitor@pam!rackpulse
  token_secret: changeme
  verify_ssl: false
```

Requires passwordless SSH from the machine running RackPulse to the PVE host. GPU power is **card draw only** — add ~50–100 W for CPU/PSU overhead, or add an `hp_server` entry if the box has a BMC.

### PDU SNMP divisor

Confirm scaling with a live walk on your PDU:

```bash
snmpwalk -v2c -c public <pdu-ip> 1.3.6.1.4.1.318.1.1.26.4.3.1.5
```

Adjust `pdu.power_divisor` in config until readings match expected kW.

### PVE API token

Create a read-only token in the Proxmox UI with **`Sys.Audit`** and **`VM.Audit`** (the built-in `PVEAuditor` role works). With **Privilege Separation** enabled on the token, assign that role to the token itself (e.g. `root@pam!rackpulse` on path `/`).

Each PVE device only needs `host`, `token_id`, and `token_secret` — the Proxmox **node name is auto-detected** by matching `host` to the node's network addresses. Set `node:` only if you need to override.

### Server BMC (Redfish)

Used for `hp_server`, `dell_server`, and `lenovo_server`. Set `verify_ssl: false` for default self-signed BMC certificates.

## Commands

```bash
rackpulse poll [--json]     # single poll, table or JSON output
rackpulse watch             # continuous terminal dashboard
rackpulse test <device>     # test connectivity for one device
rackpulse list              # list racks and devices from config
rackpulse serve             # optional HTTP API (requires pip install -e '.[api]')
```

## Configuration

All settings live in `config.yaml`. Racks contain devices; each device has a `type` and type-specific fields.

```yaml
racks:
  - name: rack-1
    location: datacenter row 1
    warning_kw: 4.0
    critical_kw: 5.0
    devices:
      - name: pdu-1
        type: pdu
        host: 192.168.1.10
        community: public
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

History is stored in SQLite at `storage.path` (default `./data/rackpulse.db`).

## Optional API

```bash
pip install -e ".[api]"
rackpulse serve
```

Endpoints:

- `GET /api/health` — no auth
- `GET /api/status` — current readings
- `POST /api/refresh` — force poll

Auth is disabled by default. Enable in config when exposing beyond localhost:

```yaml
auth:
  enabled: true
  api_key: your-secret-key
```

Requests then require header `X-API-Key: your-secret-key`.

## Docker (optional)

```bash
cp config.example.yaml config.yaml
docker compose up rackpulse        # HTTP API on :8080
docker compose --profile watch run --rm rackpulse-watch   # terminal watch
```

## Project layout

```
rackpulse/
  cli.py              Terminal commands
  config.py           YAML configuration
  storage.py          SQLite history
  snmp_client.py      SNMP helpers
  collectors/         Device-specific collectors
  engine/poller.py    Multi-rack polling engine
  display/terminal.py Rich dashboard
  api/                Optional FastAPI + auth stub
```

## License

MIT
