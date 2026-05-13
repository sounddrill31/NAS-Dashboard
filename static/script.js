        const { createApp, ref, onMounted, onUnmounted, watch, nextTick } = Vue
        createApp({
            setup() {
                const activeTab = ref('services')
                const isAdmin = ref(false)
                const localIp = ref('...')
                const publicIp = ref('...')
                const systemStatus = ref({ podman: true, compose: true })
                const services = ref({})
                const selectedUnit = ref(null)
                const currentLogs = ref('')
                const showCredits = ref(false)
                const commandOutput = ref(null)
                const serviceMap = {
                    cockpit: 'cockpit.socket', novnc: 'novnc.service', nginx: 'nginx.service',
                    sshd: 'sshd.service', tailscaled: 'tailscaled.service'
                }
                
                // State for features
                const quadletFiles = ref([]); const selectedQuadlet = ref(null);
                const proxyFiles = ref([]); const containers = ref([]);
                const composeFiles = ref([]); const selectedCompose = ref(null);
                const currentComposeLogs = ref(''); const firewallRules = ref([]);
                const apps = ref([]); const repoUrl = ref(''); const tsAuthKey = ref('');
                const showInstallModal = ref(false); const installForm = ref({ id: '', name: '', container_content: '', route: '', port: '' });
                const userList = ref([]); const newUser = ref({ username: '', password: '' });
                const userMsg = ref(''); const newPort = ref(''); const newDirection = ref('IN');

                // Editor state
                const editingFile = ref(null); const editorType = ref('compose');
                const currentAppId = ref(null); const currentAppFileType = ref(null);
                const saveStatus = ref(''); let editorInstance = null; let intervalId = null;

                const checkAuth = async () => {
                    try {
                        const res = await fetch('/api/auth/status')
                        const data = await res.json()
                        if (!data.authenticated) window.location.href = '/login'
                        isAdmin.value = data.isAdmin
                        startDashboard()
                    } catch (e) { window.location.href = '/login' }
                }

                const logout = async () => {
                    await fetch('/api/auth/logout', { method: 'POST' })
                    window.location.href = '/login'
                }

                const startDashboard = () => {
                    fetchNetwork(); fetchServices();
                    intervalId = setInterval(() => {
                        if (activeTab.value === 'services') fetchServices()
                        if (activeTab.value === 'docker') fetchContainers()
                        if (activeTab.value === 'apps') fetchApps()
                    }, 5000)
                }

                const fetchNetwork = async () => {
                    try {
                        const [pub, loc, check] = await Promise.all([
                            fetch('/api/public-ip').then(r => r.text()),
                            fetch('/api/local-ip').then(r => r.text()),
                            fetch('/api/system/check').then(r => r.json())
                        ])
                        publicIp.value = pub; localIp.value = loc; systemStatus.value = check;
                    } catch (e) {}
                }

                const fetchServices = async () => {
                    const res = await fetch('/api/services')
                    if(res.ok) services.value = await res.json()
                }

                const getStatusClass = (status) => status === 'active' ? 'bg-black' : 'bg-transparent'
                
                const controlService = async (unit, action) => {
                    await fetch('/api/control', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ unit, action })
                    })
                    setTimeout(fetchServices, 1000)
                }

                const fetchLogs = async (unit) => {
                    currentLogs.value = ''
                    const res = await fetch(`/api/logs?unit=${unit}`)
                    if(res.ok) currentLogs.value = await res.text()
                }

                const toggleLogs = (unit) => {
                    if (selectedUnit.value === unit) selectedUnit.value = null
                    else { selectedUnit.value = unit; fetchLogs(unit); }
                }

                const fetchQuadlets = async () => {
                    const res = await fetch('/api/podman/quadlets')
                    if(res.ok) quadletFiles.value = await res.json()
                }

                const toggleQuadletLogs = (file) => {
                    const unit = file.replace('.container', '.service')
                    if (selectedQuadlet.value === file) selectedQuadlet.value = null
                    else { selectedQuadlet.value = file; fetchLogs(unit); }
                }

                const openQuadletEditor = async (file) => {
                    editingFile.value = file; editorType.value = 'quadlet'
                    const res = await fetch(`/api/podman/quadlets/read?file=${file}`)
                    await setupEditor(res.ok ? await res.text() : '', 'ini')
                }

                const removeQuadlet = async (file) => {
                    if(!confirm(`Remove ${file}?`)) return
                    await fetch('/api/podman/quadlets/remove', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file })
                    })
                    fetchQuadlets()
                }

                const createNewQuadlet = () => {
                    const name = prompt("Filename (e.g. app.container):")
                    if(name && name.endsWith('.container')) openQuadletEditor(name)
                }

                const fetchProxies = async () => {
                    const res = await fetch('/api/nginx/proxies')
                    if(res.ok) proxyFiles.value = await res.json()
                }

                const openProxyEditor = async (file) => {
                    editingFile.value = file; editorType.value = 'proxy'
                    const res = await fetch(`/api/nginx/proxies/read?file=${file}`)
                    await setupEditor(res.ok ? await res.text() : '', 'nginx')
                }

                const removeProxy = async (file) => {
                    if(!confirm(`Remove ${file}?`)) return
                    await fetch('/api/nginx/proxies/remove', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file })
                    })
                    fetchProxies()
                }

                const createNewProxy = () => {
                    const name = prompt("Filename (e.g. app.conf):")
                    if(name && name.endsWith('.conf')) openProxyEditor(name)
                }

                const fetchApps = async () => {
                    const res = await fetch('/api/apps')
                    if (res.ok) apps.value = await res.json()
                }

                const installApp = async (app) => {
                    installForm.value = { 
                        id: app.id, 
                        name: app.name, 
                        container_content: 'Loading default configuration...', 
                        route: '/' + app.id, 
                        port: app.port || 8080 
                    };
                    showInstallModal.value = true;
                    
                    try {
                        const res = await fetch(`/api/apps/read?id=${app.id}&type=container`);
                        if (res.ok) {
                            installForm.value.container_content = await res.text();
                        } else {
                            installForm.value.container_content = '# Failed to load default container spec. Please write your own or check the repository.';
                        }
                    } catch (e) {
                        installForm.value.container_content = '# Error loading container spec.';
                    }
                }

                const confirmInstall = async () => {
                    try {
                        const res = await fetch('/api/apps/install', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(installForm.value)
                        })
                        if (res.ok) {
                            showInstallModal.value = false;
                            fetchApps();
                        } else {
                            alert("Installation failed: " + await res.text());
                        }
                    } catch (e) {
                        alert("Connection error during installation.");
                    }
                }

                const uninstallApp = async (app) => {
                    if(!confirm(`Uninstall ${app.name}?`)) return
                    await fetch('/api/apps/uninstall', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: app.id })
                    })
                    fetchApps()
                }

                const openAppEditor = async (appId, fileType) => {
                    editingFile.value = `${appId} [${fileType}]`; editorType.value = 'app'
                    currentAppId.value = appId; currentAppFileType.value = fileType
                    const res = await fetch(`/api/apps/read?id=${appId}&type=${fileType}`)
                    let lang = 'yaml'; if(fileType === 'json') lang = 'json'; if(fileType === 'container') lang = 'ini'; if(fileType === 'conf') lang = 'nginx';
                    await setupEditor(res.ok ? await res.text() : '', lang)
                }

                const createNewApp = async () => {
                    const id = prompt("App ID (lowercase):"); if(!id) return
                    const res = await fetch('/api/apps/create', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id })
                    })
                    if (res.ok) { fetchApps(); openAppEditor(id, 'json'); }
                }

                const syncApps = async () => {
                    if(!repoUrl.value) return
                    await fetch('/api/apps/sync', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: repoUrl.value })
                    })
                    fetchApps(); repoUrl.value = ''
                }

                const fetchContainers = async () => {
                    const res = await fetch('/api/podman/containers')
                    if(res.ok) containers.value = await res.json()
                }

                const fetchCompose = async () => {
                    const res = await fetch('/api/podman/compose')
                    if(res.ok) composeFiles.value = await res.json()
                }

                const fetchComposeLogs = async (file) => {
                    currentComposeLogs.value = ''
                    const res = await fetch(`/api/podman/compose/logs?file=${file}`)
                    if(res.ok) currentComposeLogs.value = await res.text()
                }

                const toggleComposeLogs = (file) => {
                    if (selectedCompose.value === file) selectedCompose.value = null
                    else { selectedCompose.value = file; fetchComposeLogs(file); }
                }

                const composeAction = async (file, action) => {
                    await fetch('/api/podman/compose/action', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file, action })
                    })
                    setTimeout(() => { fetchContainers(); if (selectedCompose.value === file) fetchComposeLogs(file); }, 2000)
                }

                const fetchFirewall = async () => {
                    const res = await fetch('/api/firewall/rules')
                    if(res.ok) firewallRules.value = await res.json()
                }

                const addFirewall = async () => {
                    if(!newPort.value) return
                    const res = await fetch('/api/firewall/add', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ port: newPort.value, direction: newDirection.value })
                    })
                    if(res.ok) { newPort.value = ''; fetchFirewall(); }
                }

                const tailscaleLogin = async () => {
                    if(!tsAuthKey.value) return
                    commandOutput.value = "Running 'tailscale up'..."
                    const res = await fetch('/api/tailscale/up', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ authkey: tsAuthKey.value })
                    })
                    const data = await res.json(); commandOutput.value = data.output;
                    if(res.ok) { tsAuthKey.value = ''; fetchServices(); }
                }

                const openNoVnc = async () => {
                    try {
                        const res = await fetch('/api/vnc/proxy', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
                        const data = await res.json()
                        if (res.ok && data.url) window.open(data.url, '_blank')
                        else alert("Failed to start noVNC proxy: " + (data.error || "Unknown error"))
                    } catch (e) {
                        alert("Connection error starting noVNC proxy.")
                    }
                }

                const createNewCompose = () => {
                    const name = prompt("Filename (e.g. app.yml):")
                    if(name && (name.endsWith('.yml') || name.endsWith('.yaml'))) openEditor(name)
                }

                const openEditor = async (file) => {
                    editingFile.value = file; editorType.value = 'compose'
                    const res = await fetch(`/api/files/read?file=${file}`)
                    await setupEditor(res.ok ? await res.text() : '', 'yaml')
                }

                const setupEditor = async (content, language) => {
                    await nextTick();
                    require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' } });
                    return new Promise((resolve) => {
                        require(['vs/editor/editor.main'], function () {
                            const container = document.getElementById('monaco-container');
                            if(!container) return resolve(false);
                            if(editorInstance) editorInstance.dispose();
                            editorInstance = monaco.editor.create(container, {
                                value: content, language: language, theme: 'vs-dark',
                                automaticLayout: true, fontFamily: 'Space Mono', fontSize: 12, minimap: { enabled: false }
                            });
                            editorInstance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveFile);
                            resolve(true);
                        });
                    });
                }

                const saveFile = async () => {
                    if(!editorInstance || !editingFile.value) return
                    saveStatus.value = 'Saving...'
                    let endpoint = '/api/files/save'
                    let payload = { file: editingFile.value, content: editorInstance.getValue() }
                    if (editorType.value === 'quadlet') endpoint = '/api/podman/quadlets/save'
                    else if (editorType.value === 'proxy') endpoint = '/api/nginx/proxies/save'
                    else if (editorType.value === 'app') {
                        endpoint = '/api/apps/save'
                        payload = { id: currentAppId.value, type: currentAppFileType.value, content: editorInstance.getValue() }
                    }
                    const res = await fetch(endpoint, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    })
                    if(res.ok) {
                        saveStatus.value = 'SAVED'; setTimeout(() => saveStatus.value = '', 2000)
                        if(editorType.value === 'quadlet') fetchQuadlets()
                        else if(editorType.value === 'proxy') fetchProxies()
                        else if(editorType.value === 'app') fetchApps()
                        else fetchCompose()
                    }
                }

                const closeEditor = () => {
                    if(editorInstance) { editorInstance.dispose(); editorInstance = null; }
                    editingFile.value = null; saveStatus.value = ''
                }

                const fetchUsers = async () => {
                    if (!isAdmin.value) return
                    const res = await fetch('/api/admin/users')
                    if (res.ok) userList.value = await res.json()
                }

                const addUser = async () => {
                    userMsg.value = 'Processing...'
                    const res = await fetch('/api/admin/users', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(newUser.value)
                    })
                    const data = await res.json()
                    if (res.ok) { userMsg.value = 'User added'; newUser.value = { username: '', password: '' }; fetchUsers(); }
                    else userMsg.value = 'Error: ' + data.error
                }

                const deleteUser = async (username) => {
                    if (!confirm(`Delete ${username}?`)) return
                    const res = await fetch(`/api/admin/users/${username}`, { method: 'DELETE' })
                    if (res.ok) fetchUsers()
                }

                watch(activeTab, (newTab) => {
                    if (newTab === 'users') fetchUsers()
                    if (newTab === 'docker') { fetchContainers(); fetchCompose(); fetchFirewall(); }
                    if (newTab === 'quadlets') fetchQuadlets()
                    if (newTab === 'proxies') fetchProxies()
                    if (newTab === 'apps') fetchApps()
                })

                onMounted(checkAuth)
                return {
                    activeTab, isAdmin, localIp, publicIp, systemStatus, services, serviceMap, getStatusClass,
                    controlService, selectedUnit, currentLogs, toggleLogs, fetchLogs,
                    quadletFiles, selectedQuadlet, fetchQuadlets, toggleQuadletLogs, removeQuadlet, openQuadletEditor, createNewQuadlet,
                    proxyFiles, fetchProxies, openProxyEditor, removeProxy, createNewProxy,
                    apps, repoUrl, fetchApps, installApp, confirmInstall, showInstallModal, installForm, uninstallApp, openAppEditor, createNewApp, syncApps,
                    containers, composeFiles, selectedCompose, currentComposeLogs, fetchContainers, fetchCompose, toggleComposeLogs, composeAction,
                    firewallRules, newPort, newDirection, fetchFirewall, addFirewall,
                    tsAuthKey, commandOutput, tailscaleLogin, openNoVnc,
                    editingFile, saveStatus, saveFile, closeEditor, openEditor, createNewCompose,
                    showCredits, logout, userList, newUser, userMsg, fetchUsers, addUser, deleteUser
                }
            }
        }).mount('#app')
