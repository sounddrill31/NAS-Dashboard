import pytest
import json
import os
import shutil
import tempfile
from app import app, APPS_DIR, QUADLET_DIR, NGINX_DIR


@pytest.fixture(autouse=True)
def mock_dirs(monkeypatch):
    import app
    # Create temp dirs for testing
    import tempfile

    test_dir = tempfile.mkdtemp()
    apps_dir = os.path.join(test_dir, 'apps')
    quadlet_dir = os.path.join(test_dir, 'quadlet')
    nginx_dir = os.path.join(test_dir, 'nginx')

    os.makedirs(apps_dir)
    os.makedirs(quadlet_dir)
    os.makedirs(nginx_dir)

    # Create a dummy app
    searxng_dir = os.path.join(apps_dir, 'searxng')
    os.makedirs(searxng_dir)
    with open(os.path.join(searxng_dir, 'app.json'), 'w') as f:
        json.dump({"name": "SearXNG", "port": 8080}, f)
    with open(os.path.join(searxng_dir, 'searxng.container'), 'w') as f:
        f.write("[Container]")
    with open(os.path.join(searxng_dir, 'searxng.conf'), 'w') as f:
        f.write("server {}")

    monkeypatch.setattr(app, 'APPS_DIR', apps_dir)
    monkeypatch.setattr(app, 'QUADLET_DIR', quadlet_dir)
    monkeypatch.setattr(app, 'NGINX_DIR', nginx_dir)

    yield

    shutil.rmtree(test_dir)

@pytest.fixture
def client():

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_list_apps_empty(client, monkeypatch):
    import app
    import tempfile
    empty_dir = tempfile.mkdtemp()
    monkeypatch.setattr(app, 'APPS_DIR', empty_dir)
    try:
        response = client.get('/api/apps')
        assert response.status_code == 200
        assert json.loads(response.data) == []
    finally:
        shutil.rmtree(empty_dir)

def test_list_apps(client):
    # Ensure apps directory has the dummy data
    response = client.get('/api/apps')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) > 0
    names = [d['name'] for d in data]
    assert 'SearXNG' in names

# Mock subprocess for install/uninstall testing
import subprocess
original_run = subprocess.run

def mock_run(*args, **kwargs):
    return subprocess.CompletedProcess(args=args[0], returncode=0)

def test_install_uninstall(client, monkeypatch):
    monkeypatch.setattr(subprocess, "run", mock_run)

    # Test Install
    install_resp = client.post('/api/apps/install', json={"id": "searxng"})
    assert install_resp.status_code == 200

    import app

    # Check if files were copied
    assert os.path.exists(os.path.join(app.QUADLET_DIR, 'searxng.container'))
    assert os.path.exists(os.path.join(app.NGINX_DIR, 'searxng.conf'))

    # Test Uninstall
    uninstall_resp = client.post('/api/apps/uninstall', json={"id": "searxng"})
    assert uninstall_resp.status_code == 200

    # Check if files were removed
    assert not os.path.exists(os.path.join(app.QUADLET_DIR, 'searxng.container'))
    assert not os.path.exists(os.path.join(app.NGINX_DIR, 'searxng.conf'))

def test_sync_apps(client, monkeypatch):
    calls = []
    def mock_run_capture(*args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run_capture)

    sync_resp = client.post('/api/apps/sync', json={"url": "https://github.com/example/repo.git"})
    assert sync_resp.status_code == 200

    # Check if git clone/pull was called
    assert any('git' in call and 'clone' in call or 'pull' in call for call in calls)

if __name__ == '__main__':
    pytest.main(['-v', 'test_apps.py'])
