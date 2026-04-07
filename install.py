import os
import sys
import subprocess
import shutil
import urllib.request
import socket

# Configuration
INSTALL_DIR = "/opt/nas-dashboard"
SYSTEMD_FILE = "/etc/systemd/system/nas-dashboard.service"
AVAHI_FILE = "/etc/avahi/services/nasypeasy.service"
EXTERNAL_RESOURCES = {
    "static/vue.global.js": "https://unpkg.com/vue@3/dist/vue.global.js",
    "static/tailwind.min.js": "https://cdn.tailwindcss.com"
}

def check_root():
    if os.geteuid() != 0:
        print("❌ Error: This script must be run with sudo/root privileges.")
        sys.exit(1)

def fetch_resources():
    print("📦 Fetching external resources...")
    os.makedirs("static", exist_ok=True)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    for path, url in EXTERNAL_RESOURCES.items():
        # Force download to ensure we have the latest/correct version during updates
        print(f"  - Downloading {path} from {url}...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
        except Exception as e:
            if os.path.exists(path):
                print(f"  ⚠️ Warning: Failed to download {path}, using existing version: {e}")
            else:
                print(f"  ❌ Error: Failed to download {path}: {e}")
                sys.exit(1)

def setup_files():
    print(f"🚀 Installing/Updating files to {INSTALL_DIR}...")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    
    # Files to copy (current directory contents)
    items_to_copy = ['app.py', 'templates', 'static', 'requirements.txt']
    for item in items_to_copy:
        src = item
        dst = os.path.join(INSTALL_DIR, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif os.path.exists(src):
            shutil.copy2(src, dst)
    
    # Ensure static and compose directories are populated in the install dir
    os.makedirs(os.path.join(INSTALL_DIR, "static"), exist_ok=True)
    os.makedirs(os.path.join(INSTALL_DIR, "compose"), exist_ok=True)

def setup_venv():
    print("🐍 Setting up Python Virtual Environment...")
    venv_path = os.path.join(INSTALL_DIR, "venv")
    if not os.path.exists(venv_path):
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
    
    print("📜 Installing dependencies...")
    pip_path = os.path.join(venv_path, "bin", "pip")
    subprocess.run([pip_path, "install", "--upgrade", "pip"], check=True)
    subprocess.run([pip_path, "install", "-r", os.path.join(INSTALL_DIR, "requirements.txt")], check=True)

def setup_systemd():
    print("⚙️ Configuring systemd service...")
    service_content = f"""[Unit]
Description=NAS Dashboard Backend
After=network.target

[Service]
User=root
WorkingDirectory={INSTALL_DIR}
ExecStart={INSTALL_DIR}/venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    with open(SYSTEMD_FILE, "w") as f:
        f.write(service_content)
    
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "nas-dashboard.service"], check=True)
    subprocess.run(["systemctl", "restart", "nas-dashboard.service"], check=True)

def setup_mdns():
    print("📡 Configuring mDNS (nasypeasy.local)...")
    # Set hostname
    current_hostname = socket.gethostname()
    if current_hostname != "nasypeasy":
        print("  - Setting system hostname to 'nasypeasy'...")
        subprocess.run(["hostnamectl", "set-hostname", "nasypeasy"], check=True)
    
    # Create Avahi service file
    avahi_content = """<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">NAS Dashboard on %h</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
  </service>
</service-group>
"""
    if os.path.exists("/etc/avahi/services"):
        with open(AVAHI_FILE, "w") as f:
            f.write(avahi_content)
        subprocess.run(["systemctl", "restart", "avahi-daemon"], check=False)
    else:
        print("  ⚠️ Warning: Avahi services directory not found. Skipping mDNS service file.")

def main():
    check_root()
    fetch_resources()
    setup_files()
    setup_venv()
    setup_systemd()
    setup_mdns()
    
    # Compose provider check
    provider = shutil.which('podman-compose') or shutil.which('docker-compose')
    
    print("\n✅ Installation/Update Complete!")
    print(f"👉 Access the dashboard at http://nasypeasy.local (or http://{socket.gethostname()}.local)")
    
    if not provider:
        print("\n⚠️  WARNING: No compose provider found (podman-compose or docker-compose).")
        print("   Please install one to use the DOCKER tab features:")
        print("   - Fedora/Ublue: sudo dnf install podman-compose")
    
    print("\n📦 To use Docker/Podman management:")
    print(f"   1. Drop your compose files in {os.path.join(INSTALL_DIR, 'compose')}")
    print("   2. Ensure 'podman' and 'podman-compose' are installed.")
    print("   3. Firewall rules are managed via 'firewall-cmd' and persisted.")

if __name__ == "__main__":
    main()
