let API_URL = "http://localhost:8090";
let API_TOKEN = "";

// --- State ---
let selectedMeetingId = null;
let currentTranscriptData = null;
let currentMeetingData = null;
let allMeetings = []; // Cached for search filtering
let pollTimers = new Map(); // job_id -> interval

// --- Speaker Color Map ---
const speakerColorMap = new Map();
let speakerColorIndex = 0;

function getSpeakerClass(speaker) {
    if (!speakerColorMap.has(speaker)) {
        speakerColorMap.set(speaker, speakerColorIndex % 6);
        speakerColorIndex++;
    }
    return `speaker-${speakerColorMap.get(speaker)}`;
}

function resetSpeakerColors() {
    speakerColorMap.clear();
    speakerColorIndex = 0;
}

// --- Audio Player State ---
let audioSegments = []; // Cached parsed segments for sync

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
const searchInput = document.getElementById('search-input');

// Settings Elements
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeSettings = document.getElementById('close-settings');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const apiUrlInput = document.getElementById('api-url-input');
const apiTokenInput = document.getElementById('api-token-input');


// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    await loadConfig();
    loadMeetings();

    // Upload handlers
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => handleFileUpload(e));
    }

    // Settings handlers
    setupSettingsHandlers();

    // Search
    if (searchInput) {
        searchInput.addEventListener('input', () => filterMeetings(searchInput.value));
    }

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Toolbar buttons
    document.getElementById('btn-copy')?.addEventListener('click', copyTranscript);
    document.getElementById('btn-export')?.addEventListener('click', exportTranscript);
    document.getElementById('btn-delete')?.addEventListener('click', handleDeleteMeeting);

    // Audio player
    setupAudioPlayer();

    // Editable title
    currentTitle.addEventListener('blur', async () => {
        if (!selectedMeetingId) return;
        const newTitle = currentTitle.textContent.trim();
        if (newTitle && newTitle !== currentMeetingData?.title) {
            await saveMeetingTitle(selectedMeetingId, newTitle);
            currentMeetingData.title = newTitle;
            // Update sidebar
            const sidebarItem = meetingList.querySelector(`.meeting-item[data-id="${selectedMeetingId}"] .meeting-title`);
            if (sidebarItem) sidebarItem.textContent = newTitle;
        }
    });

    currentTitle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            currentTitle.blur();
        }
    });
});

// --- Tabs ---
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`.tab[data-tab="${tabName}"]`)?.classList.add('active');
    document.getElementById(`tab-${tabName}`)?.classList.add('active');
}

// --- Configuration ---
async function loadConfig() {
    return new Promise((resolve) => {
        chrome.storage.sync.get(['api_url', 'api_token'], (result) => {
            if (result.api_url) API_URL = result.api_url;
            if (result.api_token) API_TOKEN = result.api_token;
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
        if (event.target == settingsModal) settingsModal.style.display = 'none';
    });

    saveSettingsBtn.addEventListener('click', () => {
        const newUrl = apiUrlInput.value.trim().replace(/\/$/, "");
        const newToken = apiTokenInput.value.trim();
        if (newUrl) {
            API_URL = newUrl;
            API_TOKEN = newToken;
            chrome.storage.sync.set({ api_url: API_URL, api_token: API_TOKEN }, () => {
                settingsModal.style.display = 'none';
                loadMeetings();
            });
        }
    });
}

// --- Helper: Authenticated Fetch ---
async function authFetch(url, options = {}) {
    const headers = options.headers || {};
    if (API_TOKEN) headers['Authorization'] = `Bearer ${API_TOKEN}`;
    options.headers = headers;
    return fetch(url, options);
}

// --- Upload with Status Polling ---
async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    fileInput.value = '';

    const formData = new FormData();
    formData.append('tab_file', file);

    const metadata = {
        title: file.name.replace(/\.[^/.]+$/, ""),
        date: new Date().toISOString(),
        platform: "Upload",
        duration: 0,
        url: ""
    };
    formData.append('metadata', JSON.stringify(metadata));

    uploadBtn.textContent = 'Upload en cours...';
    uploadBtn.disabled = true;

    try {
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
        await loadMeetings();

        // Start polling for job status
        if (data.job_id) {
            startStatusPolling(data.job_id, data.meeting_id);
        }

    } catch (err) {
        console.error(err);
        alert('Erreur lors de l\'upload : ' + err.message);
    } finally {
        uploadBtn.textContent = 'Importer un fichier';
        uploadBtn.disabled = false;
    }
}

function startStatusPolling(jobId, meetingId) {
    uploadBtn.textContent = 'Transcription...';
    uploadBtn.disabled = true;

    const timer = setInterval(async () => {
        try {
            const res = await authFetch(`${API_URL}/api/status/${jobId}`);
            if (!res.ok) return;
            const job = await res.json();

            if (job.status === 'completed') {
                clearInterval(timer);
                pollTimers.delete(jobId);
                uploadBtn.textContent = 'Importer un fichier';
                uploadBtn.disabled = false;
                await loadMeetings();

                // Auto-select the completed meeting
                const el = meetingList.querySelector(`.meeting-item[data-id="${meetingId}"]`);
                if (el) selectMeeting(meetingId, el);
            } else if (job.status === 'failed') {
                clearInterval(timer);
                pollTimers.delete(jobId);
                uploadBtn.textContent = 'Importer un fichier';
                uploadBtn.disabled = false;
                await loadMeetings();
                alert('La transcription a échoué : ' + (job.error || 'erreur inconnue'));
            }
            // else still processing, keep polling
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 5000); // Poll every 5s

    pollTimers.set(jobId, timer);
}

// --- API Calls ---
async function fetchMeetings() {
    try {
        const res = await authFetch(`${API_URL}/api/transcripts?limit=50&offset=0`, { method: "GET" });
        if (res.status === 401) return { meetings: [] };
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

async function saveSegmentText(segmentId, newText) {
    try {
        const res = await authFetch(`${API_URL}/api/segments/${segmentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText }),
        });
        if (!res.ok) console.error('Failed to save segment', res.status);
    } catch (err) {
        console.error('Error saving segment:', err);
    }
}

async function saveSpeakerRename(meetingId, oldName, newName) {
    try {
        const res = await authFetch(`${API_URL}/api/meetings/${meetingId}/speakers`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: oldName, new_name: newName }),
        });
        if (!res.ok) console.error('Failed to rename speaker', res.status);
    } catch (err) {
        console.error('Error renaming speaker:', err);
    }
}

async function saveMeetingTitle(meetingId, title) {
    try {
        const res = await authFetch(`${API_URL}/api/meetings/${meetingId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        if (!res.ok) console.error('Failed to save title', res.status);
    } catch (err) {
        console.error('Error saving title:', err);
    }
}

async function deleteMeeting(meetingId) {
    try {
        const res = await authFetch(`${API_URL}/api/meetings/${meetingId}`, { method: 'DELETE' });
        return res.ok;
    } catch (err) {
        console.error('Error deleting meeting:', err);
        return false;
    }
}

// --- Rendering ---
async function loadMeetings() {
    meetingList.innerHTML = '<div class="empty-state" style="height: 50px;">Chargement...</div>';

    const data = await fetchMeetings();
    allMeetings = data.meetings;
    renderMeetingList(allMeetings);
}

function renderMeetingList(meetings) {
    meetingList.innerHTML = '';

    if (meetings.length === 0) {
        meetingList.innerHTML = '<div class="empty-state">Aucune réunion</div>';
        return;
    }

    meetings.forEach(meeting => {
        const el = document.createElement('div');
        el.className = 'meeting-item';
        el.dataset.id = meeting.id;
        if (meeting.id === selectedMeetingId) el.classList.add('active');
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

function filterMeetings(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
        renderMeetingList(allMeetings);
        return;
    }
    const filtered = allMeetings.filter(m =>
        m.title.toLowerCase().includes(q) ||
        (m.platform || '').toLowerCase().includes(q)
    );
    renderMeetingList(filtered);
}

async function selectMeeting(id, element) {
    // Stop any playing audio
    const audio = document.getElementById('audio-player');
    if (audio) { audio.pause(); audio.src = ''; }

    selectedMeetingId = id;
    document.querySelectorAll('.meeting-item').forEach(el => el.classList.remove('active'));
    element.classList.add('active');

    mainEmpty.style.display = 'none';
    detailsView.style.display = 'flex';

    const data = await fetchMeetingDetails(id);
    if (!data) return;

    const { meeting, transcript } = data;
    currentMeetingData = meeting;
    currentTranscriptData = transcript;

    // Editable title
    currentTitle.textContent = meeting.title;
    currentTitle.contentEditable = 'true';

    currentDate.textContent = new Date(meeting.date).toLocaleString();
    currentPlatform.textContent = meeting.platform || 'Inconnu';
    currentDuration.textContent = meeting.duration ? Math.round(meeting.duration / 60) + ' min' : '--';

    // Show toolbar
    document.getElementById('transcript-toolbar').style.display = 'flex';

    // Switch to transcript tab
    switchTab('transcript');

    resetSpeakerColors();
    renderTranscript(transcript);
    renderInsights(meeting.extracted_data);

    // Load audio player if audio is available
    loadAudioForMeeting(meeting.id, !!meeting.audio_file);
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

        const startTime = seg.start_time ?? seg.start ?? 0;
        const endTime = seg.end_time ?? seg.end ?? 0;
        const minutes = Math.floor(startTime / 60);
        const seconds = Math.floor(startTime % 60).toString().padStart(2, '0');

        // Store times for audio sync
        el.dataset.startTime = startTime;
        el.dataset.endTime = endTime;

        const isLocal = seg.speaker === 'Me' || seg.speaker === 'Moi';
        const colorClass = isLocal ? 'local' : getSpeakerClass(seg.speaker);

        el.innerHTML = `
      <div class="segment-time seekable" data-seek="${startTime}">${minutes}:${seconds}</div>
      <div class="segment-content">
        <div class="segment-speaker ${colorClass}">${seg.speaker}</div>
        <div class="segment-text" contenteditable="true" data-segment-id="${seg.id}">${seg.text}</div>
      </div>
    `;

        // Click timestamp to seek audio
        el.querySelector('.segment-time').addEventListener('click', () => {
            seekToTime(startTime);
        });

        // Save on blur
        const textEl = el.querySelector('.segment-text');
        textEl.addEventListener('blur', () => {
            const newText = textEl.textContent.trim();
            if (newText !== seg.text && seg.id) {
                saveSegmentText(seg.id, newText);
                seg.text = newText;
            }
        });

        // Rename speaker on click
        const speakerEl = el.querySelector('.segment-speaker');
        speakerEl.style.cursor = 'pointer';
        speakerEl.title = 'Cliquer pour renommer ce speaker';

        speakerEl.addEventListener('click', async () => {
            const newName = prompt(`Renommer "${seg.speaker}" en :`, seg.speaker);
            if (newName && newName !== seg.speaker) {
                await saveSpeakerRename(selectedMeetingId, seg.speaker, newName);
                const activeEl = meetingList.querySelector('.meeting-item.active');
                if (activeEl) selectMeeting(selectedMeetingId, activeEl);
            }
        });

        transcriptContainer.appendChild(el);
    });
}

// --- Copy / Export / Delete ---
function getFormattedText() {
    if (!currentTranscriptData || !currentTranscriptData.segments) return '';

    const segments = typeof currentTranscriptData.segments === 'string'
        ? JSON.parse(currentTranscriptData.segments)
        : currentTranscriptData.segments;

    const lines = segments.map(seg => {
        const t = seg.start_time ?? seg.start ?? 0;
        const m = Math.floor(t / 60);
        const s = Math.floor(t % 60).toString().padStart(2, '0');
        return `[${m}:${s}] ${seg.speaker}: ${seg.text}`;
    });

    let text = lines.join('\n');

    if (currentMeetingData?.extracted_data?.summary?.abstract) {
        text += '\n\n--- Résumé ---\n' + currentMeetingData.extracted_data.summary.abstract;
    }

    if (currentMeetingData?.extracted_data?.action_items?.length > 0) {
        text += '\n\n--- Actions ---\n';
        currentMeetingData.extracted_data.action_items.forEach(a => {
            text += `- ${a.owner || '?'}: ${a.description}\n`;
        });
    }

    return text;
}

function copyTranscript() {
    const text = getFormattedText();
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('btn-copy');
        btn.textContent = 'Copié !';
        setTimeout(() => btn.textContent = 'Copier', 1500);
    });
}

function exportTranscript() {
    const text = getFormattedText();
    const title = currentMeetingData?.title || 'transcript';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

async function handleDeleteMeeting() {
    if (!selectedMeetingId) return;
    if (!confirm('Supprimer cette réunion ? Cette action est irréversible.')) return;

    const ok = await deleteMeeting(selectedMeetingId);
    if (ok) {
        const audio = document.getElementById('audio-player');
        if (audio) { audio.pause(); audio.src = ''; }
        document.getElementById('audio-player-bar').style.display = 'none';

        selectedMeetingId = null;
        currentTranscriptData = null;
        currentMeetingData = null;
        currentTitle.contentEditable = 'false';
        detailsView.style.display = 'none';
        mainEmpty.style.display = 'flex';
        await loadMeetings();
    } else {
        alert('Erreur lors de la suppression.');
    }
}

function renderInsights(extractedData) {
    summaryText.textContent = "Pas de résumé disponible.";
    actionsList.innerHTML = '';
    decisionsList.innerHTML = '';

    if (!extractedData) return;

    try {
        const data = typeof extractedData === 'string'
            ? JSON.parse(extractedData)
            : extractedData;

        if (data.summary) {
            summaryText.textContent = data.summary.abstract;

            // Topics
            const topicsCard = document.getElementById('topics-card');
            const topicsList = document.getElementById('topics-list');
            if (data.summary.topics && data.summary.topics.length > 0) {
                topicsCard.style.display = 'block';
                topicsList.innerHTML = data.summary.topics.map(t =>
                    `<span class="topic-tag">${t}</span>`
                ).join(' ');
            } else {
                topicsCard.style.display = 'none';
            }
        }

        if (data.action_items && data.action_items.length > 0) {
            data.action_items.forEach(action => {
                const el = document.createElement('div');
                el.className = 'action-item';
                el.innerHTML = `
          <input type="checkbox" class="checkbox" ${action.status === 'done' ? 'checked' : ''}>
          <div class="summary-text">
            <strong>${action.owner || "Quelqu'un"}</strong>: ${action.description}
          </div>
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

// --- Audio Player ---
function setupAudioPlayer() {
    const audio = document.getElementById('audio-player');
    const playBtn = document.getElementById('audio-play-btn');
    const seekBar = document.getElementById('audio-seek');
    const volumeBar = document.getElementById('audio-volume');
    const currentTimeEl = document.getElementById('audio-current-time');
    const durationEl = document.getElementById('audio-duration');

    if (!audio || !playBtn) return;

    playBtn.addEventListener('click', () => {
        if (audio.paused) {
            audio.play();
            playBtn.innerHTML = '&#9646;&#9646;'; // pause icon
        } else {
            audio.pause();
            playBtn.innerHTML = '&#9654;'; // play icon
        }
    });

    audio.addEventListener('loadedmetadata', () => {
        seekBar.max = audio.duration;
        durationEl.textContent = formatAudioTime(audio.duration);
    });

    audio.addEventListener('timeupdate', () => {
        seekBar.value = audio.currentTime;
        currentTimeEl.textContent = formatAudioTime(audio.currentTime);
        highlightCurrentSegment(audio.currentTime);
    });

    seekBar.addEventListener('input', () => {
        audio.currentTime = parseFloat(seekBar.value);
    });

    volumeBar.addEventListener('input', () => {
        audio.volume = parseFloat(volumeBar.value);
    });

    audio.addEventListener('ended', () => {
        playBtn.innerHTML = '&#9654;';
        clearSegmentHighlight();
    });
}

function formatAudioTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

function loadAudioForMeeting(meetingId, hasAudio) {
    const playerBar = document.getElementById('audio-player-bar');
    const audio = document.getElementById('audio-player');
    const playBtn = document.getElementById('audio-play-btn');

    if (!hasAudio || !playerBar || !audio) {
        if (playerBar) playerBar.style.display = 'none';
        return;
    }

    // Build audio URL with auth
    const audioUrl = `${API_URL}/api/meetings/${meetingId}/audio`;
    audio.src = audioUrl;
    playBtn.innerHTML = '&#9654;';
    playerBar.style.display = 'flex';

    // Set auth header via fetch for the audio element
    // HTML5 audio doesn't support custom headers, so we fetch as blob
    authFetch(audioUrl)
        .then(res => {
            if (!res.ok) throw new Error('Audio not available');
            return res.blob();
        })
        .then(blob => {
            audio.src = URL.createObjectURL(blob);
        })
        .catch(() => {
            playerBar.style.display = 'none';
        });
}

function highlightCurrentSegment(currentTime) {
    const segments = transcriptContainer.querySelectorAll('.transcript-segment');
    let activeEl = null;

    segments.forEach(el => {
        const start = parseFloat(el.dataset.startTime);
        const end = parseFloat(el.dataset.endTime);
        if (currentTime >= start && currentTime < end) {
            el.classList.add('playing');
            activeEl = el;
        } else {
            el.classList.remove('playing');
        }
    });

    // Auto-scroll to active segment
    if (activeEl) {
        const container = transcriptContainer;
        const elTop = activeEl.offsetTop - container.offsetTop;
        const elBottom = elTop + activeEl.offsetHeight;
        const scrollTop = container.scrollTop;
        const viewHeight = container.clientHeight;

        if (elTop < scrollTop || elBottom > scrollTop + viewHeight) {
            activeEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

function clearSegmentHighlight() {
    transcriptContainer.querySelectorAll('.transcript-segment.playing')
        .forEach(el => el.classList.remove('playing'));
}

function seekToTime(time) {
    const audio = document.getElementById('audio-player');
    if (audio && audio.src) {
        audio.currentTime = time;
        if (audio.paused) {
            audio.play();
            document.getElementById('audio-play-btn').innerHTML = '&#9646;&#9646;';
        }
    }
}
