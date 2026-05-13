#!/bin/bash
# 🛠️ nasypeasy-ctl - Dashboard Management Wrapper
# Provides a clean interface for managing the isolated dashboard services.

USER_NAME="nasypeasy"
USER_UID=$(id -u "$USER_NAME" 2>/dev/null)

if [ -z "$USER_UID" ]; then
    echo "❌ User $USER_NAME not found. Please run install.sh first."
    exit 1
fi

# Set up the environment for systemctl --user
export XDG_RUNTIME_DIR="/run/user/$USER_UID"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_UID/bus"

COMMAND=$1
shift

case "$COMMAND" in
    status)
        sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user status nas-dashboard.service nas-nginx.service
        ;;
    start)
        sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user start nas-dashboard.service nas-nginx.service
        ;;
    stop)
        sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user stop nas-dashboard.service nas-nginx.service
        ;;
    restart)
        sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" systemctl --user restart nas-dashboard.service nas-nginx.service
        ;;
    logs)
        sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" journalctl --user -u nas-dashboard.service -f "$@"
        ;;
    shell)
        echo "🐚 Entering isolated shell as $USER_NAME..."
        sudo -u "$USER_NAME" -i
        ;;
    *)
        echo "Usage: $0 {status|start|stop|restart|logs|shell}"
        exit 1
        ;;
esac
