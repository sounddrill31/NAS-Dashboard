from flask import Flask, jsonify, request, render_template
import subprocess
import urllib.request
import socket

app = Flask(__name__)

SERVICES = {
    'cockpit': 'cockpit.socket',
    'novnc': 'novnc.service',
    'nginx': 'nginx.service',
    'sshd': 'sshd.service',
    'tailscaled': 'tailscaled.service'
}

def get_service_status(unit):
    try:
        result = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True, timeout=2)
        status = result.stdout.strip()
        # systemctl is-active returns 'active', 'inactive', 'failed', 'unknown'
        if not status:
            return "unknown"
        return status
    except Exception as e:
        return "error"

def run_systemctl_action(unit, action):
    # Security: only allow predefined services and safe actions
    if unit not in SERVICES.values():
        return False, "Invalid service"
    if action not in ['start', 'stop', 'restart']:
        return False, "Invalid action"
    
    try:
        # NOTE: For this to work without a password, the user running the flask app needs sudo nopasswd for systemctl, 
        # OR the flask app itself must be running as root via systemd. The install script will set up a systemd service running as root.
        subprocess.run(['systemctl', action, unit], check=True, timeout=10)
        return True, "Success"
    except subprocess.CalledProcessError as e:
        return False, f"Action failed: {e}"
    except Exception as e:
        return False, str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/public-ip')
def public_ip():
    try:
        # Fetching public IP using an external service
        with urllib.request.urlopen('https://api.ipify.org', timeout=3) as response:
            ip = response.read().decode('utf-8')
        return ip
    except Exception:
        return "Unknown"

@app.route('/api/local-ip')
def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't have to be reachable
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
    if unit not in SERVICES.values():
        return jsonify({"status": "error", "message": "Invalid service"}), 400
    try:
        # Fetch last 50 lines of logs using journalctl
        result = subprocess.run(['journalctl', '-u', unit, '-n', '50', '--no-pager'], capture_output=True, text=True, timeout=5)
        return result.stdout
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)
