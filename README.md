# 🚀 NAS Services Dashboard

A modern, minimal, and playful system dashboard for Ublue/Fedora immutable distros. Built with Vue.js, Tailwind CSS, and a Python Flask backend. 

## Features
- **Minimal Footprint:** Single-page frontend using Vue + Tailwind via CDN.
- **Python Backend:** Lightweight Flask server to interface with systemd.
- **Service Control:** Start, Stop, and Restart essential system services (`cockpit`, `novnc`, `nginx`, `sshd`, `tailscaled`).
- **mDNS Support:** Automatically configures your system to broadcast as `nasypeasy.local`.
- **Perpetual Uptime:** Configured out-of-the-box as a resilient `systemd` service.

## Installation

Clone the repository and run the Python install script as root:

```bash
sudo python3 install.py
```

### What the installer does:
1. Downloads external JS/CSS dependencies (Vue, Tailwind) to `/static` for local serving.
2. Installs/Updates files to `/opt/nas-dashboard`.
3. Sets up a Python virtual environment and installs requirements.
4. Registers and starts the `nas-dashboard` systemd service for autostart.
5. Configures the system hostname to `nasypeasy` and registers an Avahi mDNS service, making the dashboard available at `http://nasypeasy.local`.


## Local Development