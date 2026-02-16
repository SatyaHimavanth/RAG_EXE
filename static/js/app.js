// DOM Elements
const chatArea = document.getElementById('chatArea');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const historyList = document.getElementById('historyList');
const collectionSelect = document.getElementById('collectionSelect');
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const uploadStatus = document.getElementById('uploadStatus');

// State
let currentSessionId = null;
let messages = [];

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname === '/') {
        initChat();
    }
});

function initChat() {
    loadCollections();
    loadHistory();
    updateSendButtonState();
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (isStreaming) {
                stopGeneration();
            } else {
                sendMessage();
            }
        }
    });

    messageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') this.style.height = 'auto';
    });

    messageInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        if (this.value === '') this.style.height = 'auto';
    });

    initUpload();


    // Close context menu on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.history-item')) {
            closeAllContextMenus();
        }
    });

}

// --- API Interactions ---

async function loadCollections() {
    try {
        const res = await fetch('/api/collections');
        const collections = await res.json();

        if (collectionSelect) {
            collectionSelect.innerHTML = '<option value="">No Collection (General Chat)</option>';
            collections.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.name;
                opt.textContent = c.name;
                collectionSelect.appendChild(opt);
            });
        }
        return collections;
    } catch (e) {
        console.error("Failed to load collections", e);
    }
}

let searchTimeout;
window.debounceSearch = function (query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => loadHistory(query), 300);
}

async function loadHistory(searchQuery = '') {
    try {
        let url = '/api/history';
        if (searchQuery) url += `?search=${encodeURIComponent(searchQuery)}`;

        const res = await fetch(url);
        const history = await res.json();

        if (historyList) {
            historyList.innerHTML = '';
            history.forEach(session => {
                const el = document.createElement('div');
                el.className = 'history-item';

                el.innerHTML = `
                    <span class="chat-title" onclick="loadSession(${session.id})">${session.title || `Chat ${session.id}`}</span>
                    <button class="menu-trigger" onclick="toggleContextMenu(event, ${session.id})">
                        <i class="fas fa-ellipsis-h"></i>
                    </button>
                    <div class="context-menu" id="menu-${session.id}">
                        <div class="context-item" onclick="renameSessionPrompt(event, ${session.id}, '${session.title || ''}')">
                            <i class="fas fa-pen"></i> Rename
                        </div>
                        <div class="context-item" onclick="archiveSession(event, ${session.id})">
                            <i class="fas fa-archive"></i> Archive
                        </div>
                        <div class="context-item danger" onclick="deleteSession(event, ${session.id})">
                            <i class="fas fa-trash"></i> Delete
                        </div>
                    </div>
                `;
                historyList.appendChild(el);
            });
        }
    } catch (e) {
        console.error("Failed to load history", e);
    }
}

// Sidebar logic
window.toggleSidebar = function () {
    document.getElementById('sidebar').classList.toggle('collapsed');
}

window.toggleContextMenu = function (e, id) {
    e.stopPropagation();
    closeAllContextMenus();
    const menu = document.getElementById(`menu-${id}`);
    if (menu) menu.classList.toggle('active');
}

function closeAllContextMenus() {
    document.querySelectorAll('.context-menu').forEach(m => m.classList.remove('active'));
}

async function ensureSession() {
    if (!currentSessionId) {
        try {
            const res = await fetch('/api/sessions', { method: 'POST' });
            const session = await res.json();
            currentSessionId = session.id;
            loadHistory();
        } catch (e) {
            console.error("Failed to create session", e);
        }
    }
    return currentSessionId;
}

window.startNewChat = function () {
    currentSessionId = null;
    messages = [];
    if (chatArea) chatArea.innerHTML = '';
    addMessage('bot', 'Hello! How can I help you today? You can select a collection to chat with your documents.');
}

async function loadSession(id) {
    currentSessionId = id;
    try {
        const res = await fetch(`/api/history/${id}`);
        const savedMessages = await res.json();

        if (chatArea) chatArea.innerHTML = '';
        messages = [];

        savedMessages.forEach(msg => {
            messages.push(msg);
            addMessage(msg.role, msg.content, false);
        });

        // Mobile sidebar auto close
        if (window.innerWidth < 768) toggleSidebar();

    } catch (e) {
        console.error("Failed to load session", e);
    }
}

window.deleteSession = async function (e, id) {
    e.stopPropagation();
    if (!confirm("Delete this chat?")) return;
    try {
        await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        if (currentSessionId === id) startNewChat();
        loadHistory();
    } catch (e) { console.error(e); }
}

window.archiveSession = async function (e, id) {
    e.stopPropagation();
    try {
        await fetch(`/api/sessions/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ archive: true })
        });
        if (currentSessionId === id) startNewChat();
        loadHistory();
    } catch (e) { console.error(e); }
}

window.renameSessionPrompt = async function (e, id, currentTitle) {
    e.stopPropagation();
    closeAllContextMenus();
    const newTitle = prompt("Enter new chat name:", currentTitle);
    if (newTitle && newTitle !== currentTitle) {
        try {
            await fetch(`/api/sessions/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });
            loadHistory();
        } catch (e) { console.error(e); }
    }
}

// --- Chat Logic ---

let currentAbortController = null;
let isStreaming = false;

async function sendMessage() {
    if (isStreaming) return;
    const content = messageInput.value.trim();
    if (!content) return;

    messageInput.value = '';
    messageInput.style.height = 'auto';

    addMessage('user', content);
    messages.push({ role: 'user', content });

    await ensureSession();

    const botMsgDiv = addMessage('bot', '<span class="typing">Thinking...</span>');
    const contentDiv = botMsgDiv.querySelector('.message-content');

    const collectionName = collectionSelect ? collectionSelect.value : null;

    // Setup AbortController for stop functionality
    currentAbortController = new AbortController();
    isStreaming = true;
    updateSendButtonState();

    const startTime = performance.now();
    let tokenCount = 0;
    let botResponse = "";

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: currentSessionId,
                messages: messages,
                collection_name: collectionName,
                stream: true
            }),
            signal: currentAbortController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        contentDiv.innerHTML = "Thinking...";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            botResponse += chunk;
            tokenCount++;

            // Check for metrics footer
            let displayResponse = botResponse;
            let metricsHtml = "";

            const metricsMarker = "\n\n[METRICS]";
            const metricsIndex = botResponse.lastIndexOf(metricsMarker);

            if (metricsIndex !== -1) {
                const metricsText = botResponse.substring(metricsIndex + metricsMarker.length);
                displayResponse = botResponse.substring(0, metricsIndex);
                metricsHtml = `<div class="metrics-footer">${metricsText}</div>`;
            }

            contentDiv.innerHTML = marked.parse(displayResponse) + metricsHtml;
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        messages.push({ role: 'assistant', content: botResponse });
        loadHistory();

    } catch (e) {
        if (e.name === 'AbortError') {
            const endTime = performance.now();
            const duration = ((endTime - startTime) / 1000).toFixed(2);
            const metricsMarker = "\n\n[METRICS]";
            const cleanPartial = botResponse.includes(metricsMarker)
                ? botResponse.split(metricsMarker)[0]
                : botResponse;
            if (cleanPartial.trim()) {
                messages.push({ role: 'assistant', content: cleanPartial.trim() });
            }
            const currentContent = contentDiv.innerHTML || marked.parse(cleanPartial || "");
            contentDiv.innerHTML = currentContent +
                `<div class="interrupted-msg">Stopped due to User interruption</div>` +
                `<div class="metrics-footer">Time: ${duration}s | Tokens: ~${tokenCount}</div>`;
            loadHistory();
        } else {
            contentDiv.textContent = "Error: " + e.message;
        }
    } finally {
        isStreaming = false;
        currentAbortController = null;
        updateSendButtonState();
    }
}

function stopGeneration() {
    if (currentAbortController) {
        currentAbortController.abort();
    }
}

function updateSendButtonState() {
    if (!sendBtn) return;
    if (isStreaming) {
        sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
        sendBtn.classList.add('stop-mode');
    } else {
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        sendBtn.classList.remove('stop-mode');
    }
    sendBtn.onclick = isStreaming ? stopGeneration : sendMessage;
}

function addMessage(role, content, animate = true) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

    let displayContent = content;
    if (role === 'assistant' || role === 'bot') {
        if (!content.includes('<span class="typing">')) {
            if (typeof marked !== 'undefined') {
                displayContent = marked.parse(content);
            }
        }
    }

    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">${displayContent}</div>
    `;

    if (chatArea) {
        chatArea.appendChild(div);
        chatArea.scrollTop = chatArea.scrollHeight;
    }
    return div;
}

// --- File Upload Logic ---

let stagedFiles = [];

function initUpload() {
    const fileInput = document.getElementById('fileInput');
    const openModalBtn = document.getElementById('openUploadModalBtn');
    const addFilesBtn = document.getElementById('addFilesBtn');
    const uploadBtn = document.getElementById('startUploadBtn');

    if (openModalBtn) {
        openModalBtn.addEventListener('click', () => {
            if (!collectionSelect.value) {
                alert("Please select a collection first.");
                return;
            }
            openModal('filesModal');
        });
    }

    if (addFilesBtn) {
        addFilesBtn.addEventListener('click', () => fileInput.click());
    }

    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            for (let file of e.target.files) {
                stagedFiles.push(file);
            }
            renderStagedFiles();
            fileInput.value = '';
        });
    }

    if (uploadBtn) {
        uploadBtn.addEventListener('click', handleMultiUpload);
    }
}

function renderStagedFiles() {
    const stagingArea = document.getElementById('fileStagingArea');
    const uploadBtn = document.getElementById('startUploadBtn');
    if (!stagingArea) return;

    stagingArea.innerHTML = '';
    stagedFiles.forEach((file, index) => {
        const div = document.createElement('div');
        div.className = 'file-item';
        div.innerHTML = `
            <span>${file.name}</span>
            <i class="fas fa-times file-remove" onclick="removeFile(${index})"></i>
        `;
        stagingArea.appendChild(div);
    });

    if (uploadBtn) {
        uploadBtn.style.display = stagedFiles.length > 0 ? 'inline-block' : 'none';
    }
}

window.removeFile = function (index) {
    stagedFiles.splice(index, 1);
    renderStagedFiles();
}

async function handleMultiUpload() {
    if (stagedFiles.length === 0) return;
    if (!collectionSelect.value) {
        alert("Please select a collection first.");
        return;
    }

    const uploadStatus = document.getElementById('uploadStatus');
    const uploadBtn = document.getElementById('startUploadBtn');

    uploadStatus.textContent = "Starting upload...";
    uploadBtn.disabled = true;

    const formData = new FormData();
    formData.append('collection_name', collectionSelect.value);

    // Get summarize toggle value
    const summarizeToggle = document.getElementById('summarizeToggle');
    formData.append('summarize', summarizeToggle ? summarizeToggle.checked : false);

    stagedFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);

                    if (data.status === 'embedding' && data.progress) {
                        if (uploadStatus) uploadStatus.textContent = `${data.message || 'Embedding...'}`;
                    } else if (data.status === 'summary_started') {
                        if (typeof notifications !== 'undefined') {
                            notifications.add(data.message, 'info', data.task_id);
                        }
                    } else {
                        // General status update, prevent "undefined"
                        if (data.message && uploadStatus) {
                            uploadStatus.textContent = `${data.message}`;
                        }
                    }

                    if (data.status === 'completed') {
                        // uploadStatus.textContent = "Upload Complete!";
                    }
                } catch (e) {
                    console.error("JSON parse error:", line);
                }
            }
        }

        // Clear staging after done
        setTimeout(() => {
            if (uploadStatus) uploadStatus.textContent = 'Upload Complete';
            stagedFiles = [];
            renderStagedFiles();
            closeModal('filesModal');
        }, 1000);

    } catch (error) {
        if (uploadStatus) uploadStatus.textContent = `Error: ${error.message}`;
    } finally {
        uploadBtn.disabled = false;
        fileInput.value = '';
    }
}

// Reuse Manage Page Logic
async function loadCollectionsManage() {
    const grid = document.getElementById('collectionsGrid');
    if (!grid) return;

    const collections = await loadCollections();
    grid.innerHTML = '';

    collections.forEach(c => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
            <h3>${c.name}</h3>
            <p>Ready for chat</p>
            <div id="summary-${c.name}" class="collection-summary" style="font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.5rem;"></div>
            <div style="display:flex; gap:0.5rem;">
                <button class="action-btn" onclick="openUploadModal('${c.name}')">Add Doc</button>
                <button class="action-btn" onclick="fetchSummary('${c.name}')">Summarize</button>
                <button class="btn-danger" onclick="deleteCollection('${c.name}')">Delete</button>
            </div>
        `;
        grid.appendChild(card);
    });
}
window.fetchSummary = async function (name) {
    const modal = document.getElementById('summaryModal');
    const title = document.getElementById('summaryModalTitle');
    const list = document.getElementById('summaryList');

    if (title) title.textContent = `Summaries: ${name}`;
    if (list) list.innerHTML = '<div style="text-align:center; padding:2rem;">Loading summaries...</div>';

    openModal('summaryModal');

    try {
        const res = await fetch(`/api/collections/${name}/summary`);
        const data = await res.json();

        if (list) {
            list.innerHTML = '';
            if (data.documents && data.documents.length > 0) {
                data.documents.forEach(doc => {
                    const item = document.createElement('div');
                    item.className = 'summary-item';
                    item.innerHTML = `
                        <h4>${doc.filename}</h4>
                        <div class="summary-content">${doc.summary}</div>
                    `;
                    list.appendChild(item);
                });
            } else {
                list.innerHTML = '<div style="text-align:center; padding:2rem;">No documents found or no summaries available.</div>';
            }
        }
    } catch (e) {
        if (list) list.innerHTML = `<div style="text-align:center; color:red; padding:2rem;">Error: ${e.message}</div>`;
    }
}

function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('active');
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
}

async function createCollection() {
    const nameInput = document.getElementById('newCollectionName');
    const name = nameInput.value.trim();
    if (!name) return;

    try {
        const res = await fetch('/api/collections', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });

        if (res.ok) {
            closeModal('createCollectionModal');
            nameInput.value = '';
            loadCollectionsManage();
        } else {
            alert("Failed to create collection");
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteCollection(name) {
    if (!confirm(`Delete collection "${name}"?`)) return;

    try {
        const res = await fetch(`/api/collections/${name}`, {
            method: 'DELETE'
        });

        if (res.ok) {
            loadCollectionsManage();
        }
    } catch (e) {
        console.error(e);
    }
}



let uploadTargetCollection = null;

window.openUploadModal = function (collectionName) {
    uploadTargetCollection = collectionName;
    const targetNameEl = document.getElementById('uploadTargetName');
    if (targetNameEl) targetNameEl.textContent = collectionName;
    openModal('uploadModal');
}

// --- Notification System ---
class NotificationSystem {
    constructor() {
        this.notifications = [];
        this.badge = document.getElementById('notificationBadge');
        this.list = document.getElementById('notificationList');
        this.dropdown = document.getElementById('notificationDropdown');
        this.pollInterval = null;

        this.loadNotifications();
    }

    async loadNotifications() {
        try {
            const res = await fetch('/api/notifications');
            const data = await res.json();
            this.notifications = data.notifications;
            this.render();
            this.updateBadge();
            this.checkPolling();
        } catch (e) {
            console.error("Failed to load notifications", e);
        }
    }

    async add(message, type = 'info', taskId = null) {
        // We'll reload to get the ID from server if we were to POST, 
        // but for now we expect backend to have created it or we just add a temp one.
        // Actually, for consistency, let's just reload from server or valid local add.
        // Since backend already added it to DB for 'summary_started', we just reload.
        await this.loadNotifications();
    }

    // Polling Logic
    checkPolling() {
        const hasProcessing = this.notifications.some(n => n.status === 'processing');
        if (hasProcessing && !this.pollInterval) {
            this.pollInterval = setInterval(() => this.loadNotifications(), 2000);
        } else if (!hasProcessing && this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    render() {
        if (!this.list) return;
        this.list.innerHTML = '';
        if (this.notifications.length === 0) {
            this.list.innerHTML = '<div style="padding:1rem; text-align:center; color:var(--text-secondary);">No new notifications</div>';
            return;
        }

        this.notifications.forEach(n => {
            const div = document.createElement('div');
            // Unread if not read AND not processing (processing tasks always vivid?) 
            // actually just use is_read
            div.className = `notification-item ${n.is_read ? '' : 'unread'}`;

            let progressHtml = '';
            if (n.status === 'processing' || n.progress > 0) {
                progressHtml = `
                    <div class="notif-progress">
                        <div class="notif-progress-bar" style="width: ${n.progress}%"></div>
                    </div>
                    <div style="font-size:0.7rem; text-align:right; margin-top:2px;">${n.progress}%</div>
                `;
            }

            div.innerHTML = `
                <div style="display:flex; justify-content:space-between;">
                   <span>${n.message}</span>
                   ${n.status === 'processing' ? '<i class="fas fa-spinner fa-spin"></i>' : ''}
                </div>
                ${progressHtml}
                <div style="font-size:0.7rem; margin-top:0.3rem; opacity:0.7;">
                    ${new Date(n.timestamp).toLocaleTimeString()}
                </div>
            `;
            // Click to read
            div.onclick = () => this.markRead(n.id);
            this.list.appendChild(div);
        });
    }

    async markRead(id) {
        const n = this.notifications.find(x => x.id === id);
        if (n && !n.is_read) {
            try {
                await fetch(`/api/notifications/${id}/read`, { method: 'POST' });
                n.is_read = true;
                this.render();
                this.updateBadge();
            } catch (e) { console.error(e); }
        }
    }

    updateBadge() {
        const unread = this.notifications.filter(n => !n.is_read).length;
        if (this.badge) {
            this.badge.textContent = unread;
            this.badge.style.display = unread > 0 ? 'block' : 'none';
        }
    }

    async markAllRead() {
        // Optimistic update
        this.notifications.forEach(n => n.is_read = true);
        this.render();
        this.updateBadge();
        // Fire and forget (or await if needed)
        // Ideally we'd have an endpoint for mark all
    }
}

const notifications = new NotificationSystem();

window.toggleNotifications = function () {
    const dd = document.getElementById('notificationDropdown');
    if (dd) {
        dd.classList.toggle('active');
        // We don't mark all read on toggle anymore, user clicks items or we add a "Mark All Read" button
        // For now, let's keep it manual
    }
}

window.clearNotifications = async function () {
    if (!confirm("Clear read notifications?")) return;
    try {
        await fetch('/api/notifications/clear', { method: 'POST' });
        notifications.loadNotifications();
    } catch (e) { console.error(e); }
}

window.uploadFileFromManage = async function () {
    const input = document.getElementById('manageFileInput');
    const status = document.getElementById('manageUploadStatus');
    const file = input.files[0];

    if (!file) return;

    const formData = new FormData();
    formData.append('files', file);
    formData.append('collection_name', uploadTargetCollection);

    // Get summarize toggle value from manage page
    const summarizeToggle = document.getElementById('manageSummarizeToggle');
    formData.append('summarize', summarizeToggle ? summarizeToggle.checked : false);

    status.textContent = "Starting...";

    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const data = JSON.parse(line);
                    status.textContent = `${data.message}`;
                    if (data.status === 'completed') {
                        setTimeout(() => {
                            closeModal('uploadModal');
                            status.textContent = "";
                            input.value = "";
                        }, 1000);
                    }
                    if (data.status === 'summary_started') {
                        notifications.add(data.message, 'info');
                    }
                } catch (e) {
                    console.error("JSON parse error", line);
                }
            }
        }
    } catch (e) {
        status.textContent = "Error: " + e.message;
    }
}
