# RackPulse

Multi-rack power and infrastructure monitoring for PDUs, HP/Dell/Lenovo servers, PVE nodes, NAS, switches, and GPU hosts. Stores history locally, shows a live terminal dashboard, and optionally serves a web dashboard with alerting.

Evolved from [PDU-Power-Monitor](https://github.com/DaHyper/PDU-Power-Monitor) — same rack dashboard UX, RackPulse backend for all device types.

**Setup guides:** [Mac](MAC_SETUP.md) · [Linux (CLI)](LINUX_SETUP.md)

## Install matrix

| Install | What you get |
|---------|----------------|
| `pip install -e .` | CLI, terminal dashboard, polling engine (no HTTP deps) |
| `pip install -e ".[api]"` | JSON HTTP API |
| `pip install -e ".[web]"` | Web dashboard + config UI + API |
| `pip install -e ".[everything]"` | Same as `[web]` (convenience alias) |

Alert delivery (email + webhooks) is built into the core package and activates when configured in `config.yaml`.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

cp config.example.yaml config.yaml
# Edit config.yaml — use $secret for passwords (stored in data/secrets.db)

rackpulse list
rackpulse test pdu-1
rackpulse poll
rackpulse watch
```

## Web dashboard (optional)

```bash
pip install -e ".[web]"
rackpulse serve --web
```

- Dashboard: `http://127.0.0.1:8080/`
- Config UI: `http://127.0.0.1:8080/config`

Enable auth before exposing beyond localhost:

```yaml
auth:
  enabled: true
  api_key: $secret   # stored in data/secrets.db when saved via config UI
```

The browser prompts for your API key on first visit (stored in session storage).

## Secrets (passwords outside config.yaml)

Sensitive values use `$secret` in `config.yaml` and are stored in a local SQLite secrets database (default `./data/secrets.db`):

```yaml
secrets:
  path: ./data/secrets.db

devices:
  - name: hp-server
    type: hp_server
    password: $secret
```

The config UI writes secrets to the database automatically. Config export never includes plaintext passwords.

You can also use environment variables: `password: $env:MY_BMC_PASSWORD`

## Alerting (optional)

Configure in `config.yaml`:

```yaml
alerts:
  cooldown_minutes: 15
  smtp:
    host: smtp.company.com
    port: 587
    security: tls
    username: alerts@company.com
    password: $secret
    from_address: rackpulse@company.com
    recipients:
      - ops@company.com
  webhooks:
    - name: Ops Slack
      url: https://hooks.slack.com/services/...
      format: slack
      enabled: true

maintenance:
  enabled: false
  silence_alerts: true
  message: ""
  until: null
```

Alerts fire on rack **Warning/Danger** threshold crossings, device unreachable events, and recoveries. Cooldown prevents repeat notifications. Maintenance mode suppresses delivery while polling continues.

## Device types

| Type | What it covers | Metrics |
|------|----------------|---------|
| `pdu` | Rack PDU (SNMP) | Power (W), energy (kWh) |
| `hp_server` | HP server BMC (iLO / Redfish) | Power (W), temperature |
| `dell_server` | Dell server BMC (iDRAC / Redfish) | Power (W), temperature |
| `lenovo_server` | Lenovo server BMC (XCC / Redfish) | Power (W), temperature |
| `pve` | Proxmox VE node | CPU/RAM, VM inventory |
| `nas` | NAS appliance (SNMP) | CPU, RAM, temperature |
| `arista_switch` / `cisco_switch` / `dell_switch` | Switches (ENTITY-SENSOR-MIB) | Power (W), volts, amps |
| `gpu` | GPU workstation (nvidia-smi) | GPU power, utilization |

See `config.example.yaml` for full examples (PVE tokens, GPU over SSH, PDU divisors, etc.).

## Commands

```bash
rackpulse poll [--json]
rackpulse watch
rackpulse test <device>
rackpulse history <device> [--hours 168]
rackpulse list
rackpulse serve              # JSON API only ([api])
rackpulse serve --web        # dashboard + config UI ([web])
```

## Migration from PDU-Power-Monitor

| Legacy key | RackPulse key |
|------------|---------------|
| `racks[].pdus[]` | `racks[].devices[]` with `type: pdu` |
| `racks[].description` | `racks[].location` |
| `racks[].warning_kw` / `critical_kw` | same |
| `snmp.power_oid` / `power_divisor` | `pdu.power_oid` / `pdu.power_divisor` |
| `alert_cooldown_minutes` | `alerts.cooldown_minutes` |
| `smtp` / `webhooks` | `alerts.smtp` / `alerts.webhooks` |
| `maintenance` | same |
| Plaintext passwords | `$secret` (stored in `data/secrets.db`) |

Run the web UI with `rackpulse serve --web` for the same dashboard experience, now covering all RackPulse device types.

## Docker

```bash
cp config.example.yaml config.yaml
docker compose up rackpulse   # web dashboard + API on :8080
```

## Project layout

```
rackpulse/
  cli.py                 Terminal commands
  config.py              YAML configuration + secrets resolution
  secrets.py             SQLite secrets store
  storage.py             SQLite history
  collectors/            Device-specific collectors
  engine/poller.py       Polling engine + alert hook
  display/terminal.py    Rich terminal dashboard
  presentation/          Dashboard JSON for web UI
  alerts/                Email + webhook delivery
  api/                   FastAPI (JSON + optional web routes)
  web/                   Dashboard templates + static assets
```

## License

MIT
