import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

class DashboardInstaller:
    EXTERNAL_RESOURCES = {
        "static/vue.global.js": "https://unpkg.com/vue@3/dist/vue.global.js",
        "static/tailwind.min.js": "https://cdn.tailwindcss.com"
    }

    def __init__(self, install_dir: Path, port: int, target_user: Optional[str] = None):
        self.install_dir = install_dir
        self.port = port
        self.target_user = target_user
        self.repo_root = Path(__file__).parent.absolute()

    def get_target_uid(self) -> int:
        if not self.target_user: return os.getuid()
        import pwd
        return pwd.getpwnam(self.target_user).pw_uid

    def get_target_home(self) -> Path:
        if not self.target_user: return Path.home()
        import pwd
        return Path(pwd.getpwnam(self.target_user).pw_dir)

    def fetch_resources(self):
        print("📦 Fetching external resources...")
        static_dir = self.repo_root / "static"
        static_dir.mkdir(exist_ok=True)
        
        headers = {'User-Agent': 'NAS-Dashboard-Installer/1.0'}
        for path_str, url in self.EXTERNAL_RESOURCES.items():
            path = self.repo_root / path_str
            print(f"  - Downloading {path.name}...")
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req) as response:
                    path.write_bytes(response.read())
            except Exception as e:
                if not path.exists():
                    raise RuntimeError(f"Failed to fetch {url}: {e}")
                print(f"  ⚠️ Warning: Using existing {path.name} due to fetch error.")

    def setup_submodules(self):
        print("🖇️  Initializing Git submodules...")
        try:
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], check=True)
            print("  ✅ Submodules initialized.")
        except Exception as e:
            print(f"  ⚠️ Failed to initialize submodules: {e}")

    def deploy_files(self):
        print(f"🚀 Deploying files to {self.install_dir}...")
        self.install_dir.mkdir(parents=True, exist_ok=True)
        
        items = ['app.py', 'templates', 'static', 'apps', 'pixi.toml', 'pixi.lock']
        for item in items:
            src = self.repo_root / item
            dst = self.install_dir / item
            if not src.exists(): continue
            
            if src.is_dir():
                if dst.exists(): shutil.rmtree(dst)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns('.git*', '__pycache__'))
            else:
                shutil.copy2(src, dst)
        
        (self.install_dir / "compose").mkdir(exist_ok=True)
        (self.install_dir / "nginx/conf.d").mkdir(parents=True, exist_ok=True)
        (self.install_dir / "nginx/logs").mkdir(parents=True, exist_ok=True)
        
        # Deploy nginx.conf.template
        nginx_conf_src = self.repo_root / "templates/nginx/nginx.conf.template"
        nginx_conf_dst = self.install_dir / "nginx/nginx.conf"
        if nginx_conf_src.exists():
            if nginx_conf_dst.exists(): nginx_conf_dst.unlink()
            shutil.copy2(nginx_conf_src, nginx_conf_dst)

        # Handle ownership if installing for another user
        if self.target_user and os.getuid() == 0:
            import pwd, grp
            uid = pwd.getpwnam(self.target_user).pw_uid
            gid = pwd.getpwnam(self.target_user).pw_gid
            for root, dirs, files in os.walk(self.install_dir):
                for d in dirs: os.chown(os.path.join(root, d), uid, gid)
                for f in files: os.chown(os.path.join(root, f), uid, gid)
            os.chown(self.install_dir, uid, gid)

    def setup_environment(self):
        print("❄️  Initializing Pixi environment...")
        target_home = self.get_target_home()
        pixi_exe = target_home / ".pixi/bin/pixi"
        
        if not pixi_exe.exists():
             pixi_found = shutil.which('pixi')
             pixi_exe = Path(pixi_found) if pixi_found else None

        if not pixi_exe or not pixi_exe.exists():
            print("❌ Pixi not found. Please run install.sh first or install pixi manually.")
            sys.exit(1)
        
        try:
            cmd = [str(pixi_exe), "install", "--frozen"]
            if self.target_user and os.getuid() == 0:
                subprocess.run(["sudo", "-u", self.target_user, "bash", "-c", f"cd {self.install_dir} && {' '.join(cmd)}"], check=True)
            else:
                subprocess.run(cmd, cwd=self.install_dir, check=True)
        except subprocess.CalledProcessError:
            print("❌ Pixi installation failed.")
            sys.exit(1)

    def configure_user_service(self):
        print(f"⚙️ Configuring user-level systemd service for {self.target_user or os.getlogin()}...")
        target_home = self.get_target_home()
        pixi_exe = target_home / ".pixi/bin/pixi"
        
        if not pixi_exe.exists():
            pixi_found = shutil.which('pixi')
            pixi_exe = Path(pixi_found) if pixi_found else "pixi"

        service_template = f"""[Unit]
Description=NAS Dashboard (User Level)
After=network.target

[Service]
WorkingDirectory={self.install_dir}
ExecStart={pixi_exe} run --frozen --manifest-path {self.install_dir}/pixi.toml start
Restart=always
RestartSec=5
Environment=PORT={self.port}

[Install]
WantedBy=default.target
"""
        user_systemd_dir = target_home / ".config/systemd/user"
        user_systemd_dir.mkdir(parents=True, exist_ok=True)
        
        service_file = user_systemd_dir / "nas-dashboard.service"
        service_file.write_text(service_template)
        
        nginx_service_template = f"""[Unit]
Description=NAS Dashboard Nginx (User Level)
After=network.target

[Service]
WorkingDirectory={self.install_dir}
ExecStart={pixi_exe} run --frozen --manifest-path {self.install_dir}/pixi.toml run-nginx
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
        nginx_service_file = user_systemd_dir / "nas-nginx.service"
        nginx_service_file.write_text(nginx_service_template)
        
        if self.target_user and os.getuid() == 0:
            import pwd
            uid = pwd.getpwnam(self.target_user).pw_uid
            gid = pwd.getpwnam(self.target_user).pw_gid
            os.chown(service_file, uid, gid)
            os.chown(nginx_service_file, uid, gid)
            for p in [target_home / ".config", target_home / ".config/systemd", user_systemd_dir]:
                if p.exists(): os.chown(p, uid, gid)

        print(f"  - Registering services at {user_systemd_dir}...")
        try:
            if self.target_user and os.getuid() == 0:
                target_uid = self.get_target_uid()
                env = f"XDG_RUNTIME_DIR=/run/user/{target_uid}"
                subprocess.run(["sudo", "-u", self.target_user, "bash", "-c", f"{env} systemctl --user daemon-reload"], check=True)
                subprocess.run(["sudo", "-u", self.target_user, "bash", "-c", f"{env} systemctl --user enable nas-dashboard.service nas-nginx.service"], check=True)
                subprocess.run(["sudo", "-u", self.target_user, "bash", "-c", f"{env} systemctl --user restart nas-dashboard.service nas-nginx.service"], check=True)
            else:
                subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
                subprocess.run(['systemctl', '--user', 'enable', 'nas-dashboard.service', 'nas-nginx.service'], check=True)
                subprocess.run(['systemctl', '--user', 'restart', 'nas-dashboard.service', 'nas-nginx.service'], check=True)
        except Exception as e:
            print(f"  ⚠️ Service registration failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="NAS Dashboard Installer")
    parser.add_argument("--user", help="Target system user (e.g. nasypeasy)")
    parser.add_argument("--dir", help="Installation directory")
    parser.add_argument("--port", type=int, default=8000, help="Flask port")
    args = parser.parse_args()

    target_user = args.user or os.environ.get('TARGET_USER')
    
    if target_user:
        import pwd
        try:
            pinfo = pwd.getpwnam(target_user)
            default_dir = Path(pinfo.pw_dir) / ".local/share/nas-dashboard"
        except KeyError:
            print(f"❌ User '{target_user}' does not exist. Run install.sh first.")
            sys.exit(1)
    else:
        default_dir = Path.home() / ".local/share/nas-dashboard"

    install_path = Path(args.dir or default_dir)
    installer = DashboardInstaller(install_path, args.port, target_user)
    
    try:
        installer.fetch_resources()
        installer.setup_submodules()
        installer.deploy_files()
        installer.setup_environment()
        installer.configure_user_service()
        
        user_display = target_user or os.getlogin()
        print(f"\n✅ Installation for user '{user_display}' completed successfully!")
    except Exception as e:
        print(f"\n❌ Installation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
