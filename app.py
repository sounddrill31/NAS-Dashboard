from flask import Flask, jsonify, request, render_template
import subprocess
import urllib.request
import socket
import os
import json
import re
import shutil

app = Flask(__name__)

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

for d in [COMPOSE_DIR, QUADLET_DIR, NGINX_DIR]:
    if not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except:
            pass

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

@app.route('/api/system/check')
def system_check():
    return jsonify({
        "podman": bool(shutil.which('podman')),
        "compose": bool(shutil.which('podman-compose') or shutil.which('docker-compose'))
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
