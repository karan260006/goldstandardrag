const API_URL = '/api';

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const chatOutput = document.getElementById('chat-output');
const backendStatus = document.getElementById('backend-status');
const notifications = document.getElementById('notifications');

let isUploading = false;
let isQuerying = false;

// Initialize
checkBackendHealth();
setInterval(checkBackendHealth, 10000);

// --- Backend Health ---
async function checkBackendHealth() {
    try {
        const response = await fetch(`${API_URL}/health`);
        const data = await response.json();
        if (data.status === 'healthy') {
            backendStatus.classList.add('online');
            backendStatus.innerHTML = '<span class="status-dot"></span> Backend Online';
        }
    } catch (error) {
        backendStatus.classList.remove('online');
        backendStatus.innerHTML = '<span class="status-dot"></span> Backend Offline';
    }
}

// --- File Upload ---
dropZone.onclick = () => fileInput.click();

dropZone.ondragover = (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#d4af37';
};

dropZone.ondragleave = () => {
    dropZone.style.borderColor = 'rgba(212, 175, 55, 0.2)';
};

dropZone.ondrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
};

fileInput.onchange = (e) => {
    const file = e.target.files[0];
    if (file) handleUpload(file);
};

async function handleUpload(file) {
    if (isUploading) return;
    if (!file.name.endsWith('.pdf')) {
        showNotification('Only PDF files are supported.', 'error');
        return;
    }

    isUploading = true;
    showNotification(`Uploading ${file.name}...`, 'info');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Upload failed');

        const data = await response.json();
        addFileToList(file.name);
        showNotification('Document indexed successfully!', 'success');
        
        // Remove welcome message if it exists
        const welcome = document.querySelector('.welcome-message');
        if (welcome) welcome.remove();

    } catch (error) {
        showNotification(error.message, 'error');
    } finally {
        isUploading = false;
        fileInput.value = '';
    }
}

function addFileToList(name) {
    const emptyMsg = fileList.querySelector('.empty-msg');
    if (emptyMsg) emptyMsg.remove();

    const li = document.createElement('li');
    li.innerHTML = `
        <svg style="width:18px;height:18px;fill:#d4af37" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
        <span>${name}</span>
    `;
    fileList.appendChild(li);
}

// --- Querying ---
sendBtn.onclick = submitQuery;
queryInput.onkeypress = (e) => {
    if (e.key === 'Enter') submitQuery();
};

async function submitQuery() {
    const query = queryInput.value.trim();
    if (!query || isQuerying) return;

    appendMessage('user', query);
    queryInput.value = '';
    isQuerying = true;

    // Loading indicator
    const loadingDiv = appendMessage('ai', 'Verifying documents...', true);

    try {
        const response = await fetch(`${API_URL}/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Verification failed');
        }

        const data = await response.json();
        loadingDiv.remove();
        appendMessage('ai', data.answer, false, data.sources);

    } catch (error) {
        loadingDiv.remove();
        appendMessage('ai', `Error: ${error.message}`);
        showNotification(error.message, 'error');
    } finally {
        isQuerying = false;
        chatOutput.scrollTop = chatOutput.scrollHeight;
    }
}

function appendMessage(role, text, isLoading = false, sources = []) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}-msg`;
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        sourcesHtml = '<div class="sources">' + 
            sources.map(s => `<span class="source-tag">Page ${s.metadata.page + 1}</span>`).join('') + 
            '</div>';
    }

    msgDiv.innerHTML = `
        <div class="msg-bubble">
            <div class="msg-text">${text}</div>
            ${sourcesHtml}
        </div>
    `;
    
    chatOutput.appendChild(msgDiv);
    chatOutput.scrollTop = chatOutput.scrollHeight;
    return msgDiv;
}

// --- UI Helpers ---
function showNotification(text, type) {
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = text;
    notifications.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 500);
    }, 4000);
}
