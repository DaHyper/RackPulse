# RackPulse v2.0.0 Release Notes

## What's new

- **Web dashboard** — Port of the PDU-Power-Monitor rack view (OK / Warning / Danger states, sparklines, combined gauge) backed by RackPulse's multi-device engine
- **Browser config UI** — Edit racks, devices (all types), thresholds, SNMP/PDU settings, alerts, and maintenance mode
- **Alert delivery** — Email (SMTP) and webhooks (Slack, Discord, generic JSON) on rack threshold crossings, device unreachable events, and recoveries; cooldown and maintenance suppression
- **Secrets store** — Passwords and API keys stored in `data/secrets.db`; `config.yaml` uses `$secret` references instead of plaintext
- **Config import/export** — YAML export omits secret values

## Merged from PDU-Power-Monitor

| Feature | Status |
|---------|--------|
| Web dashboard with rack states | Included |
| Config UI | Included (expanded for all device types) |
| Email + webhook alerts | Included |
| Maintenance mode | Included |
| Config export/import | Included |
| APC-only SNMP polling | **Not ported** — uses RackPulse collectors |

## Install

```bash
pip install -e .              # CLI + terminal only
pip install -e ".[api]"         # JSON HTTP API
pip install -e ".[web]"         # Dashboard + config UI + API
pip install -e ".[everything]"  # Same as [web]
```

## Upgrade from v1.x / PDU-Power-Monitor

1. Back up your existing `config.yaml`
2. Map legacy keys (see README Migration section):
   - `racks[].pdus[]` → `racks[].devices[]` with `type: pdu`
   - `snmp.power_oid` → `pdu.power_oid`
   - `smtp` / `webhooks` → `alerts.smtp` / `alerts.webhooks`
3. Run `rackpulse secrets migrate` to move plaintext passwords into `secrets.db`
4. Start the dashboard: `rackpulse dashboard` or `rackpulse serve --web`
5. Enable auth before exposing beyond localhost:

```yaml
auth:
  enabled: true
  api_key: $secret
```

## Breaking changes

- Version bumped to **2.0.0**
- Alert config moved under `alerts:` namespace
- PDU OIDs live under `pdu:` not `snmp:`
- Recommended: use `$secret` for passwords instead of inline plaintext

## Commands added

```bash
rackpulse dashboard           # web UI + API
rackpulse secrets migrate     # move plaintext creds to secrets.db
```

## Non-breaking

- `rackpulse poll`, `watch`, `test`, `history`, `list` unchanged
- `rackpulse serve` (without `--web`) still serves JSON API only
- Existing device types and collectors unchanged
