# 🚀 NAS Services Dashboard

A modern, minimal, and playful system dashboard for Ublue/Fedora immutable distros. Built with Vue.js, Tailwind CSS, and a Python Flask backend. 

## Features
- **Minimal Footprint:** Single-page frontend using Vue + Tailwind via CDN.
- **Python Backend:** Lightweight Flask server to interface with systemd.
- **Service Control:** Start, Stop, and Restart essential system services (`cockpit`, `novnc`, `nginx`, `sshd`, `tailscaled`).
- **mDNS Support:** Automatically configures your system to broadcast as `nasypeasy.local`.
- **Perpetual Uptime:** Configured out-of-the-box as a resilient `systemd` service.

## Installation

Clone the repository and run the Python install script. You can customize the installation using environment variables:

```bash
# Default installation (to /var/opt/nas-dashboard, port 8000)
sudo python3 install.py

# Custom installation example
sudo PORT=9000 INSTALL_DIR=/custom/path SKIP_SYSTEM_CONFIG=true python3 install.py
```

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