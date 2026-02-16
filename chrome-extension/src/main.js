import * as API from './api.js';
import * as Audio from './audio.js';
import * as Config from './config.js';
import { copyTranscript, exportTranscript } from './export.js';
import { startStatusPolling } from './job-poller.js';
import { setupSettingsHandlers } from './settings.js';
import state from './state.js';
import * as UI from './ui.js';

const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-upload');
const searchInput = document.getElementById('search-input');
const currentTitle = document.getElementById('current-title');

document.addEventListener('DOMContentLoaded', async () => {
    await Config.loadConfig();
    loadMeetings();

    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileUpload);
    }

    setupSettingsHandlers(loadMeetings);

    if (searchInput) {
        searchInput.addEventListener('input', () => filterMeetings(searchInput.value));
    }

    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    document.getElementById('btn-copy')?.addEventListener('click', copyTranscript);
    document.getElementById('btn-export')?.addEventListener('click', exportTranscript);
    document.getElementById('btn-delete')?.addEventListener('click', handleDeleteMeeting);

    Audio.setupAudioPlayer((time) => {
        UI.highlightCurrentSegment(time);
    });

    setupTitleEditing();
});

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
    Audio.stopAudio();

    state.selectedMeetingId = id;
    document.querySelectorAll('.meeting-item').forEach(el => el.classList.remove('active'));
    if (element) element.classList.add('active');

    document.getElementById('main-empty').style.display = 'none';
    document.getElementById('details-view').style.display = 'flex';

    const data = await API.fetchMeetingDetails(id);
    if (!data) return;

    const { meeting, transcript } = data;
    state.meetingData = meeting;
    state.transcriptData = transcript;

    currentTitle.textContent = meeting.title;
    currentTitle.contentEditable = 'true';

    document.getElementById('current-date').textContent = new Date(meeting.date).toLocaleString();
    document.getElementById('current-platform').textContent = meeting.platform || 'Inconnu';
    document.getElementById('current-duration').textContent = meeting.duration ? Math.round(meeting.duration / 60) + ' min' : '--';

    document.getElementById('transcript-toolbar').style.display = 'flex';

    switchTab('transcript');

    UI.resetSpeakerColors();
    UI.renderTranscript(transcript,
        (time) => Audio.seekToTime(time),
        handleSegmentTextChange,
        handleSpeakerRename
    );
    UI.renderInsights(meeting.extracted_data);

    Audio.loadAudioForMeeting(meeting.id, !!meeting.audio_file);
}

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
            startStatusPolling(data.job_id, data.meeting_id, { loadMeetings, selectMeeting });
        }

    } catch (err) {
        console.error(err);
        alert('Erreur lors de l\'upload : ' + err.message);
    } finally {
        uploadBtn.textContent = 'Importer un fichier';
        uploadBtn.disabled = false;
    }
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

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`.tab[data-tab="${tabName}"]`)?.classList.add('active');
    document.getElementById(`tab-${tabName}`)?.classList.add('active');
}
