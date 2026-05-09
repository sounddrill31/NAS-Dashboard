
from flask import Flask, jsonify, request, render_template, session
import subprocess
import urllib.request
import socket
import os
import json
import re
import shutil
from pysqlcipher3 import dbapi2 as sqlite
from werkzeug.security import generate_password_hash, check_password_hash



app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_flask_secret_change_me')

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow testing to bypass auth if explicitly configured
        if app.config.get('TESTING') and not app.config.get('REQUIRE_AUTH', True):
            return f(*args, **kwargs)

        if 'logged_in' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


SERVICES = {
    'cockpit': 'cockpit.socket',
    'novnc': 'novnc.service',
    'nginx': 'nginx.service',
    'sshd': 'sshd.service',
    'tailscaled': 'tailscaled.service'
}

COMPOSE_DIR = os.environ.get('COMPOSE_DIR', "/var/opt/nas-dashboard/compose")
QUADLET_DIR = os.environ.get('QUADLET_DIR', "/etc/containers/systemd")
NGINX_DIR = os.environ.get('NGINX_DIR', "/etc/nginx/conf.d")
APPS_DIR = os.environ.get('APPS_DIR', "/var/opt/nas-dashboard/apps")
AUTH_DB_PATH = os.environ.get('AUTH_DB_PATH', "./auth.db")
DB_PASSWORD = os.environ.get('DB_PASSWORD', "default_secret_key_change_me")

for d in [COMPOSE_DIR, QUADLET_DIR, NGINX_DIR, APPS_DIR]:
    if not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except:
            pass

def init_db():
    # Make sure parent dir exists
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    conn = sqlite.connect(AUTH_DB_PATH)
    conn.execute(f"PRAGMA key='{DB_PASSWORD}'")

    # Try to execute something to check if the password is correct/db is init
    try:
        conn.execute("SELECT count(*) FROM sqlite_master;")
    except sqlite.DatabaseError:
        print("Database key is incorrect or database is corrupted.")
        return

    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Create default admin user if no users exist
    cursor.execute("SELECT count(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_hash = generate_password_hash('admin')
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', default_hash))

    conn.commit()
    conn.close()

init_db()

def get_service_status(unit):
    try:
        result = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True, timeout=2)
        status = result.stdout.strip()
        if not status:
            return "unknown"
        return status
    except Exception:
        return "error"

def run_systemctl_action(unit, action):
    # Allow any .service or .socket unit if it's a quadlet or in SERVICES
    is_valid = unit in SERVICES.values() or unit.endswith('.service') or unit.endswith('.socket')
    if not is_valid:
        return False, "Invalid service"
    if action not in ['start', 'stop', 'restart', 'enable', 'disable']:
        return False, "Invalid action"
    try:
        subprocess.run(['systemctl', action, unit], check=True, timeout=10)
        return True, "Success"
    except Exception as e:
        return False, str(e)


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    try:
        conn = sqlite.connect(AUTH_DB_PATH)
        conn.execute(f"PRAGMA key='{DB_PASSWORD}'")
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if row and check_password_hash(row[0], password):
            session['logged_in'] = True
            session['username'] = username
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return jsonify({"status": "success"})

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    if app.config.get('TESTING') and not app.config.get('REQUIRE_AUTH', True):
         return jsonify({"authenticated": True})
    return jsonify({"authenticated": 'logged_in' in session})

@app.route('/')

def index():
    return render_template('index.html')

@app.route('/api/public-ip')
def public_ip():
    try:
        with urllib.request.urlopen('https://api.ipify.org', timeout=3) as response:
            return response.read().decode('utf-8')
    except Exception:
        return "Unknown"

@app.route('/api/local-ip')
def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@app.route('/api/services')
def services():
    status = {}
    for name, unit in SERVICES.items():
        status[unit] = get_service_status(unit)
    
    # Also include quadlet services if they exist
    try:
        for f in os.listdir(QUADLET_DIR):
            if f.endswith('.container'):
                unit = f.replace('.container', '.service')
                status[unit] = get_service_status(unit)
    except:
        pass

    return jsonify(status)

@app.route('/api/control', methods=['POST'])
@login_required
def control():
    data = request.json
    unit = data.get('unit')
    action = data.get('action')
    success, message = run_systemctl_action(unit, action)
    if success:
        return jsonify({"status": "success", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 400

@app.route('/api/logs')
def get_logs():
    unit = request.args.get('unit')
    # Basic validation: check if it's in SERVICES or is a quadlet-derived service
    is_valid = unit in SERVICES.values()
    if not is_valid and unit.endswith('.service'):
        # Check if corresponding .container exists
        container_file = unit.replace('.service', '.container')
        if os.path.exists(os.path.join(QUADLET_DIR, container_file)):
            is_valid = True

    if not is_valid:
        return jsonify({"status": "error", "message": "Invalid service"}), 400
    try:
        result = subprocess.run(['journalctl', '-u', unit, '-n', '50', '--no-pager'], capture_output=True, text=True, timeout=5)
        return result.stdout
    except Exception as e:
        return str(e), 500

@app.route('/api/podman/containers')
def podman_containers():
    try:
        result = subprocess.run(['podman', 'ps', '-a', '--format', 'json'], capture_output=True, text=True, timeout=5)
        return result.stdout or "[]"
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/podman/quadlets')
def list_quadlets():
    try:
        files = [f for f in os.listdir(QUADLET_DIR) if f.endswith('.container')]
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/podman/quadlets/read')
def read_quadlet():
    filename = request.args.get('file')
    if not filename: return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(QUADLET_DIR, filename))
    if not safe_path.startswith(QUADLET_DIR): return "Unauthorized", 403
    try:
        if not os.path.exists(safe_path): return ""
        with open(safe_path, 'r') as f: return f.read()
    except Exception as e: return str(e), 500

@app.route('/api/podman/quadlets/save', methods=['POST'])
@login_required
def save_quadlet():
    data = request.json
    filename = data.get('file')
    content = data.get('content')
    if not filename or content is None: return "Invalid request", 400
    if not filename.endswith('.container'):
        return "Only .container files allowed", 400
    safe_path = os.path.normpath(os.path.join(QUADLET_DIR, filename))
    if not safe_path.startswith(QUADLET_DIR): return "Unauthorized", 403
    try:
        with open(safe_path, 'w') as f: f.write(content)
        # Trigger daemon-reload to pick up changes
        subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=10)
        return jsonify({"status": "success"})
    except Exception as e: return str(e), 500

@app.route('/api/podman/quadlets/remove', methods=['POST'])
@login_required
def remove_quadlet():
    data = request.json
    filename = data.get('file')
    if not filename: return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(QUADLET_DIR, filename))
    if not safe_path.startswith(QUADLET_DIR): return "Unauthorized", 403
    try:
        if os.path.exists(safe_path):
            os.remove(safe_path)
            subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=10)
        return jsonify({"status": "success"})
    except Exception as e: return str(e), 500

@app.route('/api/nginx/proxies')
def list_proxies():
    try:
        files = [f for f in os.listdir(NGINX_DIR) if f.endswith('.conf')]
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/nginx/proxies/read')
def read_proxy():
    filename = request.args.get('file')
    if not filename: return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(NGINX_DIR, filename))
    if not safe_path.startswith(NGINX_DIR): return "Unauthorized", 403
    try:
        if not os.path.exists(safe_path): return ""
        with open(safe_path, 'r') as f: return f.read()
    except Exception as e: return str(e), 500

@app.route('/api/nginx/proxies/save', methods=['POST'])
@login_required
def save_proxy():
    data = request.json
    filename = data.get('file')
    content = data.get('content')
    if not filename or content is None: return "Invalid request", 400
    if not filename.endswith('.conf'):
        return "Only .conf files allowed", 400
    safe_path = os.path.normpath(os.path.join(NGINX_DIR, filename))
    if not safe_path.startswith(NGINX_DIR): return "Unauthorized", 403
    try:
        with open(safe_path, 'w') as f: f.write(content)
        # Check if nginx is running and reload it
        if shutil.which('nginx'):
            subprocess.run(['nginx', '-t'], check=True, timeout=5) # Test config
            subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=10)
        return jsonify({"status": "success"})
    except Exception as e: return str(e), 500

@app.route('/api/nginx/proxies/remove', methods=['POST'])
@login_required
def remove_proxy():
    data = request.json
    filename = data.get('file')
    if not filename: return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(NGINX_DIR, filename))
    if not safe_path.startswith(NGINX_DIR): return "Unauthorized", 403
    try:
        if os.path.exists(safe_path):
            os.remove(safe_path)
            if shutil.which('nginx'):
                subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=10)
        return jsonify({"status": "success"})
    except Exception as e: return str(e), 500

@app.route('/api/podman/compose')
def list_compose():
    try:
        files = [f for f in os.listdir(COMPOSE_DIR) if f.endswith('.yml') or f.endswith('.yaml')]
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/podman/compose/action', methods=['POST'])
@login_required
def compose_action():
    data = request.json
    filename = data.get('file')
    action = data.get('action')
    if not filename or action not in ['up', 'down', 'stop', 'restart']:
        return jsonify({"error": "Invalid request"}), 400
    file_path = os.path.join(COMPOSE_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    try:
        provider = None
        for p in ['podman-compose', 'docker-compose']:
            if shutil.which(p):
                provider = p
                break
        
        if not provider:
            return jsonify({"error": "Neither podman-compose nor docker-compose found. Please install podman-compose."}), 500

        cmd = [provider, '-f', file_path, action]
        if action == 'up':
            cmd.append('-d')
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return jsonify({"error": result.stderr or result.stdout}), 500
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/podman/compose/logs')
def compose_logs():
    filename = request.args.get('file')
    if not filename:
        return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(COMPOSE_DIR, filename))
    if not safe_path.startswith(COMPOSE_DIR):
        return "Unauthorized", 403
    try:
        provider = None
        for p in ['podman-compose', 'docker-compose']:
            if shutil.which(p):
                provider = p
                break
        
        if not provider:
            return "Compose provider missing (podman-compose/docker-compose)", 500

        cmd = [provider, '-f', safe_path, 'logs', '--tail', '50']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout or result.stderr or "No logs found."
    except Exception as e:
        return str(e), 500

@app.route('/api/firewall/rules')
def list_firewall():
    try:
        # Get standard (IN) ports
        res_in = subprocess.run(['firewall-cmd', '--list-ports'], capture_output=True, text=True, timeout=5)
        in_rules = [f"{p.upper()}/IN" for p in res_in.stdout.strip().split()]
        
        # Get rich rules (OUT)
        res_rich = subprocess.run(['firewall-cmd', '--list-rich-rules'], capture_output=True, text=True, timeout=5)
        out_rules = []
        for line in res_rich.stdout.strip().split('\n'):
            if not line.strip(): continue
            # Extract port and protocol from rich rule: rule family="ipv4" port port="80" protocol="tcp" accept
            m_port = re.search(r'port="(\d+)"', line)
            m_proto = re.search(r'protocol="(\w+)"', line)
            if m_port and m_proto:
                out_rules.append(f"{m_port.group(1)}/{m_proto.group(1).upper()}/OUT")
        
        return jsonify(in_rules + out_rules)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/firewall/add', methods=['POST'])
@login_required
def add_firewall():
    data = request.json
    port_spec = data.get('port') # e.g. "80/tcp"
    direction = data.get('direction', 'IN')
    if not port_spec or '/' not in port_spec:
        return jsonify({"error": "Invalid port format (use port/protocol)"}), 400
    try:
        port, proto = port_spec.split('/')
        if direction == 'IN':
            subprocess.run(['firewall-cmd', '--permanent', '--add-port', f"{port}/{proto}"], check=True, timeout=5)
        else:
            rule = f'rule family="ipv4" port port="{port}" protocol="{proto}" accept'
            subprocess.run(['firewall-cmd', '--permanent', '--add-rich-rule', rule], check=True, timeout=5)
        subprocess.run(['firewall-cmd', '--reload'], check=True, timeout=5)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tailscale/up', methods=['POST'])
@login_required
def tailscale_up():
    data = request.json
    authkey = data.get('authkey')
    if not authkey:
        return jsonify({"status": "error", "message": "Authkey required"}), 400
    try:
        result = subprocess.run(['tailscale', 'up', '--authkey', authkey, '--reset'], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return jsonify({"status": "success", "output": result.stdout or "Tailscale is up."})
        else:
            return jsonify({"status": "error", "output": result.stderr or result.stdout}), 500
    except Exception as e:
        return jsonify({"status": "error", "output": str(e)}), 500

@app.route('/api/files/read')
def read_file_content():
    filename = request.args.get('file')
    if not filename: return "Filename required", 400
    safe_path = os.path.normpath(os.path.join(COMPOSE_DIR, filename))
    if not safe_path.startswith(COMPOSE_DIR): return "Unauthorized", 403
    try:
        if not os.path.exists(safe_path): return ""
        with open(safe_path, 'r') as f: return f.read()
    except Exception as e: return str(e), 500

@app.route('/api/files/save', methods=['POST'])
@login_required
def save_file_content():
    data = request.json
    filename = data.get('file')
    content = data.get('content')
    if not filename or content is None: return "Invalid request", 400
    if not (filename.endswith('.yml') or filename.endswith('.yaml')):
        return "Only .yml or .yaml files allowed", 400
    safe_path = os.path.normpath(os.path.join(COMPOSE_DIR, filename))
    if not safe_path.startswith(COMPOSE_DIR): return "Unauthorized", 403
    try:
        with open(safe_path, 'w') as f: f.write(content)
        return jsonify({"status": "success"})
    except Exception as e: return str(e), 500


@app.route('/api/apps')
def list_apps():
    apps = []
    if not os.path.exists(APPS_DIR):
        return jsonify(apps)

    for app_dir in os.listdir(APPS_DIR):
        full_path = os.path.join(APPS_DIR, app_dir)
        if os.path.isdir(full_path):
            json_path = os.path.join(full_path, 'app.json')
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r') as f:
                        app_data = json.load(f)
                        app_data['id'] = app_dir
                        # Check status
                        is_installed = False
                        container_files = [cf for cf in os.listdir(full_path) if cf.endswith('.container')]
                        if container_files:
                            # If ANY of the container files exist in QUADLET_DIR, consider it installed
                            for cf in container_files:
                                if os.path.exists(os.path.join(QUADLET_DIR, cf)):
                                    is_installed = True
                                    break

                        app_data['installed'] = is_installed
                        apps.append(app_data)
                except Exception as e:
                    pass
    return jsonify(apps)


@app.route('/api/apps/install', methods=['POST'])
@login_required
def install_app():
    data = request.json
    app_id = data.get('id')
    if not app_id: return "App ID required", 400

    app_dir = os.path.join(APPS_DIR, app_id)
    if not os.path.exists(app_dir): return "App not found", 404

    try:
        # Install Quadlet
        container_files = [f for f in os.listdir(app_dir) if f.endswith('.container')]
        for f in container_files:
            src = os.path.join(app_dir, f)
            dst = os.path.join(QUADLET_DIR, f)
            shutil.copy2(src, dst)

        # Install Nginx Config
        conf_files = [f for f in os.listdir(app_dir) if f.endswith('.conf')]
        for f in conf_files:
            src = os.path.join(app_dir, f)
            dst = os.path.join(NGINX_DIR, f)
            shutil.copy2(src, dst)

        # Reload systemd
        if container_files:
            subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=10)
            for f in container_files:
                service_name = f.replace('.container', '.service')
                # Try to enable and start, but don't fail if it doesn't work immediately
                subprocess.run(['systemctl', 'enable', '--now', service_name], timeout=30)

        # Reload nginx
        if conf_files:
            if shutil.which('nginx'):
                subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=10)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/apps/uninstall', methods=['POST'])
@login_required
def uninstall_app():
    data = request.json
    app_id = data.get('id')
    if not app_id: return "App ID required", 400

    app_dir = os.path.join(APPS_DIR, app_id)
    if not os.path.exists(app_dir): return "App not found", 404

    try:
        container_files = [f for f in os.listdir(app_dir) if f.endswith('.container')]
        for f in container_files:
            service_name = f.replace('.container', '.service')
            try:
                subprocess.run(['systemctl', 'disable', '--now', service_name], timeout=30)
            except:
                pass
            dst = os.path.join(QUADLET_DIR, f)
            if os.path.exists(dst):
                os.remove(dst)

        conf_files = [f for f in os.listdir(app_dir) if f.endswith('.conf')]
        for f in conf_files:
            dst = os.path.join(NGINX_DIR, f)
            if os.path.exists(dst):
                os.remove(dst)

        if container_files:
            subprocess.run(['systemctl', 'daemon-reload'], check=True, timeout=10)

        if conf_files:
            if shutil.which('nginx'):
                subprocess.run(['systemctl', 'reload', 'nginx'], check=True, timeout=10)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/apps/read')
@login_required
def read_app_file():
    app_id = request.args.get('id')
    file_type = request.args.get('type') # 'json', 'container', 'conf'

    if not app_id or file_type not in ['json', 'container', 'conf']:
        return "Invalid request", 400

    app_dir = os.path.normpath(os.path.join(APPS_DIR, app_id))
    if not app_dir.startswith(APPS_DIR) or not os.path.exists(app_dir):
        return "App not found", 404

    filename = 'app.json'
    if file_type == 'container':
        filename = f"{app_id}.container"
    elif file_type == 'conf':
        filename = f"{app_id}.conf"

    file_path = os.path.join(app_dir, filename)

    if not os.path.exists(file_path):
        return "" # File doesn't exist yet, return empty

    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        return str(e), 500


@app.route('/api/apps/save', methods=['POST'])
@login_required
def save_app_file():
    data = request.json
    app_id = data.get('id')
    file_type = data.get('type')
    file_content = data.get('content')

    if not app_id or file_type not in ['json', 'container', 'conf'] or file_content is None:
        return "Invalid request", 400

    app_dir = os.path.normpath(os.path.join(APPS_DIR, app_id))
    if not app_dir.startswith(APPS_DIR):
        return "Unauthorized", 403

    if not os.path.exists(app_dir):
        os.makedirs(app_dir, exist_ok=True)

    filename = 'app.json'
    if file_type == 'container':
        filename = f"{app_id}.container"
    elif file_type == 'conf':
        filename = f"{app_id}.conf"

    file_path = os.path.join(app_dir, filename)

    try:
        with open(file_path, 'w') as f:
            f.write(file_content)
        return jsonify({"status": "success"})
    except Exception as e:
        return str(e), 500


@app.route('/api/apps/create', methods=['POST'])
@login_required
def create_app():
    data = request.json
    app_id = data.get('id')

    if not app_id:
        return "App ID required", 400

    app_dir = os.path.normpath(os.path.join(APPS_DIR, app_id))
    if not app_dir.startswith(APPS_DIR):
        return "Unauthorized", 403

    if os.path.exists(app_dir):
        return "App already exists", 400

    try:
        os.makedirs(app_dir)
        # Create skeleton app.json
        skeleton_json = {
            "name": app_id.capitalize(),
            "description": "A new application",
            "port": 8080
        }
        with open(os.path.join(app_dir, 'app.json'), 'w') as f:
            json.dump(skeleton_json, f, indent=2)

        # Create skeleton container
        with open(os.path.join(app_dir, f'{app_id}.container'), 'w') as f:
            f.write(f"[Unit]\nDescription={app_id} container\n\n[Container]\nImage=\nPublishPort=\n\n[Install]\nWantedBy=multi-user.target\n")

        # Create skeleton proxy
        with open(os.path.join(app_dir, f'{app_id}.conf'), 'w') as f:
            f.write(f"server {{\n    listen 80;\n    server_name {app_id}.local;\n\n    location / {{\n        proxy_pass http://127.0.0.1:8080;\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n    }}\n}}\n")

        return jsonify({"status": "success"})
    except Exception as e:
        return str(e), 500



@app.route('/api/apps/sync', methods=['POST'])
@login_required
def sync_apps():
    data = request.json
    repo_url = data.get('url')
    if not repo_url: return "Repository URL required", 400

    try:
        if os.path.exists(APPS_DIR):
            if os.path.exists(os.path.join(APPS_DIR, '.git')):
                # It's a git repo, try to pull
                subprocess.run(['git', '-C', APPS_DIR, 'remote', 'set-url', 'origin', repo_url], check=True, timeout=10)
                subprocess.run(['git', '-C', APPS_DIR, 'pull'], check=True, timeout=30)
            else:
                # Not a git repo, remove and clone
                shutil.rmtree(APPS_DIR)
                subprocess.run(['git', 'clone', repo_url, APPS_DIR], check=True, timeout=60)
        else:
            # Doesn't exist, clone
            subprocess.run(['git', 'clone', repo_url, APPS_DIR], check=True, timeout=60)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/check')


def system_check():
    return jsonify({
        "podman": bool(shutil.which('podman')),
        "compose": bool(shutil.which('podman-compose') or shutil.which('docker-compose'))
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
