import * as API from './api.js';
import * as Audio from './audio.js';
import * as Config from './config.js';
import * as UI from './ui.js';

// --- State ---
const state = {
    selectedMeetingId: null,
    transcriptData: null,
    meetingData: null,
    meetings: [],
    pollTimers: new Map(),
};

// --- Elements ---
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-upload');
const searchInput = document.getElementById('search-input');
const currentTitle = document.getElementById('current-title');

// Settings Elements
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const closeSettings = document.getElementById('close-settings');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const apiUrlInput = document.getElementById('api-url-input');
const apiTokenInput = document.getElementById('api-token-input');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    await Config.loadConfig();
    loadMeetings();

    // Upload handlers
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileUpload);
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
    Audio.setupAudioPlayer((time) => {
        UI.highlightCurrentSegment(time);
    });

    // Editable title
    setupTitleEditing();
});

// --- Logic ---

async function loadMeetings() {
    const meetingList = document.getElementById('meeting-list');
    meetingList.innerHTML = '<div class="empty-state" style="height: 50px;">Chargement...</div>';

    const data = await API.fetchMeetings();
    state.meetings = data.meetings || [];
    UI.renderMeetingList(state.meetings, state.selectedMeetingId, selectMeeting);
}

function filterMeetings(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
        UI.renderMeetingList(state.meetings, state.selectedMeetingId, selectMeeting);
        return;
    }
    const filtered = state.meetings.filter(m =>
        m.title.toLowerCase().includes(q) ||
        (m.platform || '').toLowerCase().includes(q)
    );
    UI.renderMeetingList(filtered, state.selectedMeetingId, selectMeeting);
}

async function selectMeeting(id, element) {
    Audio.stopAudio(); // Stop previous audio

    state.selectedMeetingId = id;
    // Update active class in list
    document.querySelectorAll('.meeting-item').forEach(el => el.classList.remove('active'));
    if (element) element.classList.add('active');

    document.getElementById('main-empty').style.display = 'none';
    document.getElementById('details-view').style.display = 'flex';

    const data = await API.fetchMeetingDetails(id);
    if (!data) return;

    const { meeting, transcript } = data;
    state.meetingData = meeting;
    state.transcriptData = transcript;

    // Editable title
    currentTitle.textContent = meeting.title;
    currentTitle.contentEditable = 'true';

    document.getElementById('current-date').textContent = new Date(meeting.date).toLocaleString();
    document.getElementById('current-platform').textContent = meeting.platform || 'Inconnu';
    document.getElementById('current-duration').textContent = meeting.duration ? Math.round(meeting.duration / 60) + ' min' : '--';

    // Show toolbar
    document.getElementById('transcript-toolbar').style.display = 'flex';

    // Switch to transcript tab
    switchTab('transcript');

    UI.resetSpeakerColors();
    UI.renderTranscript(transcript,
        (time) => Audio.seekToTime(time),
        handleSegmentTextChange,
        handleSpeakerRename
    );
    UI.renderInsights(meeting.extracted_data);

    // Load audio player
    Audio.loadAudioForMeeting(meeting.id, !!meeting.audio_file);
}

// --- Handlers ---

async function handleSegmentTextChange(segId, newText, seg) {
    if (segId) {
        await API.saveSegmentText(segId, newText);
        seg.text = newText;
    }
}

async function handleSpeakerRename(speakerName) {
    const newName = prompt(`Renommer "${speakerName}" en :`, speakerName);
    if (newName && newName !== speakerName) {
        await API.saveSpeakerRename(state.selectedMeetingId, speakerName, newName);
        // Refresh to update all segments
        const activeEl = document.querySelector(`.meeting-item[data-id="${state.selectedMeetingId}"]`);
        selectMeeting(state.selectedMeetingId, activeEl);
    }
}

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
        const data = await API.uploadMeetingAudio(formData);
        await loadMeetings();

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
            const job = await API.fetchJobStatus(jobId);

            if (job.status === 'completed') {
                clearInterval(timer);
                state.pollTimers.delete(jobId);
                uploadBtn.textContent = 'Importer un fichier';
                uploadBtn.disabled = false;
                await loadMeetings();

                const el = document.querySelector(`.meeting-item[data-id="${meetingId}"]`);
                if (el) selectMeeting(meetingId, el);
            } else if (job.status === 'failed') {
                clearInterval(timer);
                state.pollTimers.delete(jobId);
                uploadBtn.textContent = 'Importer un fichier';
                uploadBtn.disabled = false;
                await loadMeetings();
                alert('La transcription a échoué : ' + (job.error || 'erreur inconnue'));
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 5000);

    state.pollTimers.set(jobId, timer);
}

async function handleDeleteMeeting() {
    if (!state.selectedMeetingId) return;
    if (!confirm('Supprimer cette réunion ? Cette action est irréversible.')) return;

    if (await API.deleteMeeting(state.selectedMeetingId)) {
        Audio.stopAudio();
        state.selectedMeetingId = null;
        state.transcriptData = null;
        state.meetingData = null;
        currentTitle.contentEditable = 'false';
        document.getElementById('details-view').style.display = 'none';
        document.getElementById('main-empty').style.display = 'flex';
        await loadMeetings();
    } else {
        alert('Erreur lors de la suppression.');
    }
}

function setupTitleEditing() {
    currentTitle.addEventListener('blur', async () => {
        if (!state.selectedMeetingId) return;
        const newTitle = currentTitle.textContent.trim();
        if (newTitle && newTitle !== state.meetingData?.title) {
            await API.saveMeetingTitle(state.selectedMeetingId, newTitle);
            state.meetingData.title = newTitle;
            // Update sidebar
            const sidebarItem = document.querySelector(`.meeting-item[data-id="${state.selectedMeetingId}"] .meeting-title`);
            if (sidebarItem) sidebarItem.textContent = newTitle;
        }
    });

    currentTitle.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            currentTitle.blur();
        }
    });
}

function setupSettingsHandlers() {
    if (!settingsBtn || !settingsModal) return;

    settingsBtn.addEventListener('click', () => {
        settingsModal.style.display = 'flex';
        apiUrlInput.value = Config.getApiUrl();
        apiTokenInput.value = Config.getApiToken();
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
            Config.updateConfig(newUrl, newToken);
            chrome.storage.sync.set({ api_url: newUrl, api_token: newToken }, () => {
                settingsModal.style.display = 'none';
                loadMeetings();
            });
        }
    });
}

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`.tab[data-tab="${tabName}"]`)?.classList.add('active');
    document.getElementById(`tab-${tabName}`)?.classList.add('active');
}

// --- Utils ---

function getFormattedText() {
    if (!state.transcriptData || !state.transcriptData.segments) return '';

    const segments = typeof state.transcriptData.segments === 'string'
        ? JSON.parse(state.transcriptData.segments)
        : state.transcriptData.segments;

    const lines = segments.map(seg => {
        const t = seg.start_time ?? seg.start ?? 0;
        const m = Math.floor(t / 60);
        const s = Math.floor(t % 60).toString().padStart(2, '0');
        return `[${m}:${s}] ${seg.speaker}: ${seg.text}`;
    });

    let text = lines.join('\n');

    if (state.meetingData?.extracted_data?.summary?.abstract) {
        text += '\n\n--- Résumé ---\n' + state.meetingData.extracted_data.summary.abstract;
    }

    if (state.meetingData?.extracted_data?.action_items?.length > 0) {
        text += '\n\n--- Actions ---\n';
        state.meetingData.extracted_data.action_items.forEach(a => {
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
    const title = state.meetingData?.title || 'transcript';
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}
