let API_URL = "http://localhost:8090"; // Default, will be updated from storage
let API_TOKEN = ""; // Default empty

// --- State ---
let selectedMeetingId = null;

// --- Elements ---
const meetingList = document.getElementById('meeting-list');
const currentTitle = document.getElementById('current-title');
const currentDate = document.getElementById('current-date');
const currentPlatform = document.getElementById('current-platform');
const currentDuration = document.getElementById('current-duration');
const detailsView = document.getElementById('details-view');
const mainEmpty = document.getElementById('main-empty');
const transcriptContainer = document.getElementById('transcript-container');
const summaryText = document.getElementById('summary-text');
const actionsList = document.getElementById('actions-list');
const decisionsList = document.getElementById('decisions-list');
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-upload');

// Settings Elements
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeSettings = document.getElementById('close-settings');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const apiUrlInput = document.getElementById('api-url-input');
const apiTokenInput = document.getElementById('api-token-input');


// --- Initialization ---
console.log('Main.js loaded');
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOMContentLoaded fired');

    // Load config
    await loadConfig();

    // Initial fetch
    loadMeetings();

    // Upload handlers
    if (uploadBtn && fileInput) {
        console.log('Attaching upload listeners');
        uploadBtn.addEventListener('click', (e) => {
            console.log('Upload btn clicked');
            fileInput.click();
        });
        fileInput.addEventListener('change', (e) => {
            console.log('File selected', e.target.files);
            handleFileUpload(e);
        });
    } else {
        console.error('Upload elements not found', { uploadBtn, fileInput });
    }

    // Settings handlers
    setupSettingsHandlers();
});

// --- Configuration ---
async function loadConfig() {
    return new Promise((resolve) => {
        chrome.storage.sync.get(['api_url', 'api_token'], (result) => {
            if (result.api_url) {
                API_URL = result.api_url;
                console.log('Loaded API URL from storage:', API_URL);
            } else {
                console.log('Using default API URL:', API_URL);
            }
            if (result.api_token) {
                API_TOKEN = result.api_token;
                console.log('Loaded API Token from storage');
            }

            // Update input placeholder/value
            if (apiUrlInput) apiUrlInput.value = API_URL;
            if (apiTokenInput) apiTokenInput.value = API_TOKEN;
            resolve();
        });
    });
}

function setupSettingsHandlers() {
    if (!settingsBtn || !settingsModal) return;

    settingsBtn.addEventListener('click', () => {
        settingsModal.style.display = 'flex';
        apiUrlInput.value = API_URL;
        apiTokenInput.value = API_TOKEN;
    });

    closeSettings.addEventListener('click', () => {
        settingsModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target == settingsModal) {
            settingsModal.style.display = 'none';
        }
    });

    saveSettingsBtn.addEventListener('click', () => {
        const newUrl = apiUrlInput.value.trim().replace(/\/$/, ""); // Remove trailing slash
        const newToken = apiTokenInput.value.trim();

        if (newUrl) {
            API_URL = newUrl;
            API_TOKEN = newToken;

            chrome.storage.sync.set({ api_url: API_URL, api_token: API_TOKEN }, () => {
                console.log('Saved Configuration');
                settingsModal.style.display = 'none';
                // Refresh list with new URL/Token
                loadMeetings();
                alert('Configuration enregistrée !');
            });
        }
    });
}

// --- Helper: Authenticated Fetch ---
async function authFetch(url, options = {}) {
    const headers = options.headers || {};
    if (API_TOKEN) {
        headers['Authorization'] = `Bearer ${API_TOKEN}`;
    }
    options.headers = headers;
    return fetch(url, options);
}

// --- Actions ---
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Reset input
    fileInput.value = '';

    const formData = new FormData();
    formData.append('tab_file', file); // Use as tab file (main audio)

    // Create minimal metadata
    const metadata = {
        title: file.name.replace(/\.[^/.]+$/, ""), // Remove extension
        date: new Date().toISOString(),
        platform: "Upload",
        duration: 0, // Unknown initially
        url: ""
    };
    formData.append('metadata', JSON.stringify(metadata));

    uploadBtn.textContent = 'Upload en cours...';
    uploadBtn.disabled = true;

    try {
        // Use authFetch but we need to handle FormData headers carefully
        // fetch automatically ignores Content-Type for FormData if not set, which is what we want
        // So we manually construct headers for auth
        const headers = {};
        if (API_TOKEN) headers['Authorization'] = `Bearer ${API_TOKEN}`;

        const res = await fetch(`${API_URL}/api/upload`, {
            method: 'POST',
            headers: headers,
            body: formData
        });

        if (res.status === 401) throw new Error('Non autorisé (vérifiez votre token)');
        if (!res.ok) throw new Error('Upload failed');

        const data = await res.json();
        console.log('Upload success:', data);

        // Refresh list
        await loadMeetings();
        alert('Fichier importé avec succès. La transcription a commencé.');

    } catch (err) {
        console.error(err);
        alert('Erreur lors de l\'upload : ' + err.message);
    } finally {
        uploadBtn.textContent = 'Importer un fichier';
        uploadBtn.disabled = false;
    }
}

// --- API Calls ---
async function fetchMeetings() {
    try {
        const res = await authFetch(`${API_URL}/api/transcripts?limit=50&offset=0`, {
            method: "GET"
        });
        if (res.status === 401) {
            console.error("Unauthorized fetchMeetings");
            return { meetings: [] }; // Silent fail or handle UI
        }
        if (!res.ok) throw new Error("Failed to fetch meetings");
        return await res.json();
    } catch (err) {
        console.error(err);
        return { meetings: [] };
    }
}

async function fetchMeetingDetails(id) {
    try {
        const res = await authFetch(`${API_URL}/api/transcripts/${id}`);
        if (res.status === 401) throw new Error("Unauthorized");
        if (!res.ok) throw new Error("Failed to fetch details");
        return await res.json();
    } catch (err) {
        console.error(err);
        return null;
    }
}

// --- Rendering ---
async function loadMeetings() {
    meetingList.innerHTML = '<div class="empty-state" style="height: 50px;">Chargement...</div>';

    const data = await fetchMeetings();
    meetingList.innerHTML = '';

    if (data.meetings.length === 0) {
        meetingList.innerHTML = '<div class="empty-state">Aucune réunion</div>';
        return;
    }

    data.meetings.forEach(meeting => {
        const el = document.createElement('div');
        el.className = 'meeting-item';
        el.onclick = () => selectMeeting(meeting.id, el);

        const date = new Date(meeting.date).toLocaleDateString();

        el.innerHTML = `
      <div class="meeting-date">${date}</div>
      <div class="meeting-title">${meeting.title}</div>
      <div class="meeting-meta">
        <span>${meeting.duration ? Math.round(meeting.duration / 60) + ' min' : '--'}</span>
        <span class="status-badge ${meeting.status}">${meeting.status}</span>
      </div>
    `;
        meetingList.appendChild(el);
    });
}

async function selectMeeting(id, element) {
    document.querySelectorAll('.meeting-item').forEach(el => el.classList.remove('active'));
    element.classList.add('active');

    mainEmpty.style.display = 'none';
    detailsView.style.display = 'flex';

    const data = await fetchMeetingDetails(id);
    if (!data) return;

    const { meeting, transcript } = data;

    currentTitle.textContent = meeting.title;
    currentDate.textContent = new Date(meeting.date).toLocaleString();
    currentPlatform.textContent = meeting.platform || 'Iconnu';
    currentDuration.textContent = meeting.duration ? Math.round(meeting.duration / 60) + ' min' : '--';

    renderTranscript(transcript);
    renderInsights(transcript.structured_data);
}

function renderTranscript(transcriptData) {
    transcriptContainer.innerHTML = '';

    if (!transcriptData || !transcriptData.segments) {
        transcriptContainer.innerHTML = '<div class="empty-state">Aucun transcript disponible</div>';
        return;
    }

    const segments = typeof transcriptData.segments === 'string'
        ? JSON.parse(transcriptData.segments)
        : transcriptData.segments;

    segments.forEach(seg => {
        const el = document.createElement('div');
        el.className = 'transcript-segment';

        const minutes = Math.floor(seg.start / 60);
        const seconds = Math.floor(seg.start % 60).toString().padStart(2, '0');

        const isLocal = seg.speaker === 'Me' || seg.speaker === 'Moi';

        el.innerHTML = `
      <div class="segment-time">${minutes}:${seconds}</div>
      <div class="segment-content">
        <div class="segment-speaker ${isLocal ? 'local' : ''}">${seg.speaker}</div>
        <div class="segment-text">${seg.text}</div>
      </div>
    `;
        transcriptContainer.appendChild(el);
    });
}

function renderInsights(structuredDataStr) {
    summaryText.textContent = "Pas de résumé disponible.";
    actionsList.innerHTML = '';
    decisionsList.innerHTML = '';

    if (!structuredDataStr) return;

    try {
        const data = typeof structuredDataStr === 'string'
            ? JSON.parse(structuredDataStr)
            : structuredDataStr;

        if (data.summary) {
            summaryText.textContent = data.summary.abstract;
        }

        if (data.action_items && data.action_items.length > 0) {
            data.action_items.forEach(action => {
                const el = document.createElement('div');
                el.className = 'action-item';
                el.innerHTML = `
          <input type="checkbox" class="checkbox" ${action.status === 'done' ? 'checked' : ''}>
          <div class="summary-text">
            <strong>${action.owner || "Quelqu'un"}</strong>: ${action.description}
          </div >
                    `;
                actionsList.appendChild(el);
            });
        } else {
            actionsList.innerHTML = '<div class="insight-item">Aucune action détectée</div>';
        }

        if (data.decisions && data.decisions.length > 0) {
            data.decisions.forEach(decision => {
                const el = document.createElement('li');
                el.className = 'insight-item';
                el.textContent = decision.decision;
                decisionsList.appendChild(el);
            });
        } else {
            decisionsList.innerHTML = '<li class="insight-item">Aucune décision majeure</li>';
        }

    } catch (e) {
        console.error("Failed to parse structured data", e);
        summaryText.textContent = "Erreur lors du chargement des insights.";
    }
}
