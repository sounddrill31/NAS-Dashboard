# Host Repository Structure

To add external applications to your NAS Dashboard, you can provide an external repository (a Git repository URL or a local folder path).

The repository should contain a list of folders, each representing an application. Each application folder must contain at least an `app.json` file. It can optionally contain a `.container` file for Podman Quadlet support and a `.conf` file for Nginx proxy configuration.

## Folder Structure

```
repository-root/
├── app1/
│   ├── app.json
│   ├── app1.container (optional)
│   └── app1.conf (optional)
├── app2/
│   ├── app.json
│   ├── app2.container (optional)
│   └── app2.conf (optional)
└── ...
```

## `app.json` Schema

The `app.json` file describes the application and contains its metadata.

```json
{
  "name": "App Name",
  "description": "A brief description of what the app does.",
  "port": 8080
}
```

- **`name`** (string, required): The display name of the application.
- **`description`** (string, optional): A short description of the application.
- **`port`** (integer, optional): The main port the application uses (for display purposes).

## `.container` File (Quadlet)

A Podman Quadlet `.container` file allows the application to be managed via `systemd`. It will be automatically deployed to the Quadlet configuration directory (e.g., `/etc/containers/systemd`).

Example (`uptime-kuma.container`):
```ini
[Unit]
Description=Uptime Kuma container

[Container]
Image=docker.io/louislam/uptime-kuma:1
Volume=uptime-kuma:/app/data
PublishPort=3001:3001

[Install]
WantedBy=multi-user.target
```

## `.conf` File (Nginx)

An Nginx configuration file can be provided to automatically route traffic to the application via a proxy. This file will be deployed to the Nginx configuration directory (e.g., `/etc/nginx/conf.d`).

Example (`uptime-kuma.conf`):
```nginx
server {
    listen 80;
    server_name uptime.local;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
