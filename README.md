# 🚀 NAS Services Dashboard

A modern, minimal, and playful system dashboard for Ublue/Fedora immutable distros. Built with Vue.js, Tailwind CSS, and a Python Flask backend. 

## Features
- **Minimal Footprint:** Single-page frontend using Vue + Tailwind via CDN.
- **Python Backend:** Lightweight Flask server to interface with systemd.
- **Service Control:** Start, Stop, and Restart essential system services (`cockpit`, `novnc`, `nginx`, `sshd`, `tailscaled`).
- **mDNS Support:** Automatically configures your system to broadcast as `nasypeasy.local`.
- **Perpetual Uptime:** Configured out-of-the-box as a resilient `systemd` service.


## Installation

### Prerequisites
Before installing, ensure the following system services are installed via your system package manager (they do not need to be running, but must be installed):
- `cockpit`
- `tailscale` (`tailscaled`)

Example for Fedora/Ublue:
```bash
sudo dnf install cockpit tailscale
```

### ⚡ Quick Start (Unprivileged)

Install **Pixi**, then set up the dashboard in your home directory:

```bash
# 1. Install Pixi
curl -fsSL https://pixi.sh/install.sh | bash

# 2. Run the User-Level Setup
pixi run setup-dashboard

# 3. (Optional) Run Privileged Setup (Linger, Firewall, Hostname)
pixi run setup-privileged
```

The dashboard will be running as a user service at `~/.config/systemd/user/nas-dashboard.service`.

### Fallback Access
- **Local**: `http://localhost:8000/`
- **Branded**: `http://localhost:8000/nasypeasy`

### Configuration Variables:
- `INSTALL_DIR`: Where the app files will be stored (default: `/var/opt/nas-dashboard`)
- `PORT`: The port the Flask app will run on (default: `8000`)
- `SKIP_SYSTEM_CONFIG`: Set to `true` to skip `systemctl` and `hostnamectl` commands (useful for dry-runs or limited environments)

### What the installer does:
1. Downloads external JS/CSS dependencies (Vue, Tailwind) to `/static` for local serving.
2. Installs/Updates files to your specified `INSTALL_DIR`.
3. Sets up a Python virtual environment and installs requirements.
4. Registers and starts the `nas-dashboard` systemd service for autostart (unless skipped).
5. Configures the system hostname to `nasypeasy` and registers an Avahi mDNS service (unless skipped).


## Local Development