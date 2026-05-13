#!/bin/bash
# 🛠️ NASy-Peasy Dashboard - Isolated User Setup
# Creates a dedicated system user and handles privileged configuration.

set -e

if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script as root: sudo bash install.sh"
  exit 1
fi

USER_NAME="nasypeasy"
PORT=${PORT:-8000}

echo "🔒 NASy-Peasy: Initializing Isolated User Setup..."

# 0. Check Dependencies
echo "🔍 Checking dependencies..."
if ! systemctl list-unit-files | grep -q 'cockpit.socket\|cockpit.service'; then
    echo "❌ cockpit is not installed."
    echo "   Please install it using your system package manager (e.g., sudo dnf install cockpit) before proceeding."
    exit 1
fi

if ! command -v tailscaled >/dev/null 2>&1 && ! systemctl list-unit-files | grep -q 'tailscaled.service'; then
    echo "❌ tailscale is not installed."
    echo "   Please install it using your system package manager before proceeding."
    exit 1
fi
echo "✅ Dependencies found."

# 1. Create Dedicated System User
if ! id "$USER_NAME" &>/dev/null; then
    echo "👤 Creating system user: $USER_NAME..."
    useradd -m -r -s /bin/bash "$USER_NAME"
    echo "  ✅ User $USER_NAME created."
else
    echo "ℹ️  User $USER_NAME already exists."
fi

# Ensure user directory permissions are correct
chown -R "$USER_NAME:$USER_NAME" "/home/$USER_NAME"

# Grant subuid and subgid for podman rootless containers
echo "🐋 Configuring rootless Podman UIDs/GIDs..."
usermod --add-subuids 100000-165535 --add-subgids 100000-165535 "$USER_NAME"
su - "$USER_NAME" -c "podman system migrate" || true


# 2. Enable User Lingering (so user services run without active sessions)
echo "🔋 Enabling user lingering for $USER_NAME..."
loginctl enable-linger "$USER_NAME"

# 3. Install Pixi for the isolated user
echo "❄️  Installing Pixi for $USER_NAME..."
su - "$USER_NAME" -c "curl -fsSL https://pixi.sh/install.sh | bash"
echo "  ✅ Pixi installed in /home/$USER_NAME/.pixi"

# 4. Configure Firewall (Optional - if firewalld is present)
if command -v firewall-cmd >/dev/null 2>&1; then
    echo "🔥 Opening ports $PORT/tcp and 6080/tcp..."
    firewall-cmd --permanent --add-port=$PORT/tcp
    firewall-cmd --permanent --add-port=6080/tcp
    firewall-cmd --reload
else
    echo "⚠️  firewalld not found, skipping port configuration."
fi

# 5. Apply mDNS Hostname (Optional - if provided)
if [ ! -z "$1" ]; then
    echo "📡 Setting system hostname to $1..."
    hostnamectl set-hostname "$1"
fi

# 6. Grant original user access to nasypeasy
if [ -n "$SUDO_USER" ]; then
    echo "🔑 Granting $SUDO_USER passwordless access to $USER_NAME..."
    echo "$SUDO_USER ALL=($USER_NAME) NOPASSWD: ALL" > "/etc/sudoers.d/$USER_NAME-admin"
    chmod 440 "/etc/sudoers.d/$USER_NAME-admin"
fi

# 7. Configure Polkit and Permissions for the Dashboard
echo "🔐 Configuring Polkit rules for $USER_NAME..."
cat <<EOF > /etc/polkit-1/rules.d/99-$USER_NAME.rules
polkit.addRule(function(action, subject) {
    if (subject.user == "$USER_NAME") {
        if (action.id == "org.freedesktop.systemd1.manage-units") {
            var unit = action.lookup("unit");
            if (unit == "cockpit.socket" || 
                unit == "sshd.service" || 
                unit == "tailscaled.service" || 
                unit == "firewalld.service" || 
                unit == "avahi-daemon.service") {
                return polkit.Result.YES;
            }
        }
        if (action.id == "org.freedesktop.hostname1.set-hostname" ||
            action.id == "org.freedesktop.hostname1.set-static-hostname") {
            return polkit.Result.YES;
        }
        if (action.id.indexOf("org.fedoraproject.FirewallD1") == 0) {
            return polkit.Result.YES;
        }
    }
});
EOF

echo "📖 Granting journal access to $USER_NAME..."
usermod -aG systemd-journal "$USER_NAME"

echo "🔑 Granting $USER_NAME sudo access for tailscale..."
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/bin/tailscale" > "/etc/sudoers.d/$USER_NAME-tailscale"
chmod 440 "/etc/sudoers.d/$USER_NAME-tailscale"

echo "🛠️ Installing nas-ctl management script to /usr/local/bin..."
cp "$(dirname "$0")/nas-ctl.sh" /usr/local/bin/nas-ctl
chmod +x /usr/local/bin/nas-ctl

echo "✅ Isolated user setup completed successfully."
echo "👉 Now install the dashboard itself:"
echo "   sudo python3 post-install.py --user $USER_NAME"
