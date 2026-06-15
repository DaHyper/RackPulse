# RackPulse — Linux setup guide (CLI)

Step-by-step instructions to run RackPulse on Linux from the terminal only.

---

## What you need first

| Requirement | Notes |
|-------------|--------|
| **Linux** | Debian/Ubuntu, RHEL/Rocky, Fedora, or similar |
| **Python 3.11+** | Check with `python3 --version` |
| **Network access to your gear** | Host must reach PDU/NAS (UDP 161), BMC/PVE (HTTPS), and GPU hosts |
| **Device details** | IPs, SNMP communities, BMC credentials, PVE API token — see `config.example.yaml` |

Optional packages:

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip snmp snmp-mip-utils curl

# RHEL / Rocky / Fedora
sudo dnf install -y python3 python3-pip net-snmp-utils curl
```

For local GPU monitoring, install NVIDIA drivers and `nvidia-smi` on the host.

---

## Step 1 — Open the project folder

If you already cloned the repo:

```bash
cd ~/RackPulse
```

If you haven't cloned it yet:

```bash
git clone <your-repo-url> RackPulse
cd RackPulse
```

---

## Step 2 — Check Python

```bash
python3 --version
```

You should see **3.11** or newer.

On older distros, install a newer Python from your package manager or [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) (Ubuntu).

---

## Step 3 — Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Run `source .venv/bin/activate` again each time you open a new shell session.

---

## Step 4 — Install RackPulse

```bash
pip install --upgrade pip
pip install -e .
```

Verify the CLI:

```bash
rackpulse --version
```

---

## Step 5 — Create your config file

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your real values:

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

      - name: dell-server
        type: dell_server
        host: 192.168.1.21
        username: bmc-user
        password: changeme
        verify_ssl: false

      - name: pve-1
        type: pve
        host: 192.168.1.30
        token_id: monitor@pam!rackpulse
        token_secret: changeme
        verify_ssl: false

      - name: nas-1
        type: nas
        host: 192.168.1.40
        community: public

      - name: gpu-workstation
        type: gpu
        host: localhost
```

> `config.yaml` is git-ignored. Keep credentials out of version control.

---

## Step 6 — Verify connectivity

### PDU (SNMP)

```bash
snmpwalk -v2c -c public 192.168.1.10 1.3.6.1.4.1.318.1.1.26.4.3.1.5
```

Confirm `pdu.power_divisor` matches your hardware (see `MAC_SETUP.md` for the divisor table).

### Server BMC (Redfish)

```bash
curl -sk -u bmc-user:changeme https://192.168.1.20/redfish/v1/Chassis/1/Power
```

### PVE

```bash
curl -sk -H "Authorization: PVEAPIToken=monitor@pam!rackpulse=changeme" \
  https://192.168.1.30:8006/api2/json/nodes
```

### NAS (SNMP)

```bash
snmpwalk -v2c -c public 192.168.1.40 1.3.6.1.4.1.2021.4.5.0
```

### GPU (local)

```bash
nvidia-smi --query-gpu=power.draw,utilization.gpu,temperature.gpu --format=csv
```

---

## Step 7 — List and test devices

```bash
rackpulse list
rackpulse test pdu-1
rackpulse test hp-server
rackpulse test dell-server
rackpulse test pve-1
rackpulse test nas-1
rackpulse test gpu-workstation
```

Fix any unreachable devices before starting continuous monitoring.

---

## Step 8 — Run RackPulse

**One-shot poll:**

```bash
rackpulse poll
```

**Live terminal dashboard:**

```bash
rackpulse watch
```

**JSON output:**

```bash
rackpulse poll --json
```

Press **Ctrl+C** to stop `watch`. History is stored in `./data/rackpulse.db`.

---

## Quick reference — every time you start it

```bash
cd ~/RackPulse
source .venv/bin/activate
rackpulse watch
```

---

## Run in the background (systemd user service)

For 24/7 polling on a Linux box without keeping a terminal open.

Create `~/.config/systemd/user/rackpulse.service`:

```ini
[Unit]
Description=RackPulse monitoring
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_USER/RackPulse
ExecStart=/home/YOUR_USER/RackPulse/.venv/bin/rackpulse watch
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now rackpulse.service
systemctl --user status rackpulse.service
```

View logs:

```bash
journalctl --user -u rackpulse.service -f
```

Replace `/home/YOUR_USER/RackPulse` with your actual path.

---

## Run in tmux (simple alternative)

```bash
tmux new -s rackpulse
source .venv/bin/activate
rackpulse watch
# Detach: Ctrl+B then D
# Reattach: tmux attach -t rackpulse
```

---

## Troubleshooting

### `python3-venv` not found (Debian/Ubuntu)

```bash
sudo apt install python3-venv
```

### `rackpulse: command not found`

```bash
source .venv/bin/activate
pip install -e .
```

### SNMP timeout

- Check `ufw` / `firewalld` — outbound UDP 161 is usually allowed by default
- Confirm community string and PDU IP
- Test with `snmpwalk` directly

### BMC / PVE HTTPS errors

Set `verify_ssl: false` in config for self-signed certificates.

### GPU collector fails

- Confirm `nvidia-smi` works as the same user running RackPulse
- For remote GPU hosts, set `host` to the IP and `ssh_user` in config; ensure passwordless SSH works

### Permission denied on `data/rackpulse.db`

```bash
mkdir -p data
chmod 755 data
```

---

## Next steps

- Place RackPulse on a management VM with network access to all racks
- Tune per-rack `warning_kw` / `critical_kw` thresholds
- Use `rackpulse poll --json` with cron or a wrapper script for custom alerting
