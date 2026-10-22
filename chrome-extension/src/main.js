import * as API from './api.js';
import * as Ask from './ask.js';
import * as Audio from './audio.js';
import * as Config from './config.js';
import { copyTranscript, exportTranscript } from './export.js';
import { applyAllProgress, applyProgress, resumeActiveJobs, startStatusPolling } from './job-poller.js';
import { setupSettingsHandlers } from './settings.js';
import state from './state.js';
import * as UI from './ui.js';

const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-upload');
const searchInput = document.getElementById('search-input');
const currentTitle = document.getElementById('current-title');
const askInput = document.getElementById('ask-input');
const askScope = document.getElementById('ask-scope-current');
const askSubmit = document.getElementById('ask-submit');

document.addEventListener('DOMContentLoaded', async () => {
    await Config.loadConfig();
    await loadMeetings();
    resumeActiveJobs({ loadMeetings, selectMeeting });

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
    setupAsk();
});

async function loadMeetings() {
    const meetingList = document.getElementById('meeting-list');
    meetingList.innerHTML = '<div class="empty-state" style="height: 50px;">Chargement...</div>';

    const data = await API.fetchMeetings();
    state.meetings = data.meetings || [];
    UI.renderMeetingList(state.meetings, state.selectedMeetingId, selectMeeting);
    applyAllProgress();
}

function filterMeetings(query) {
    const q = query.toLowerCase().trim();
    if (!q) {
        UI.renderMeetingList(state.meetings, state.selectedMeetingId, selectMeeting);
        applyAllProgress();
        return;
    }
    const filtered = state.meetings.filter(m =>
        m.title.toLowerCase().includes(q) ||
        (m.platform || '').toLowerCase().includes(q)
    );
    UI.renderMeetingList(filtered, state.selectedMeetingId, selectMeeting);
    applyAllProgress();
}

async function selectMeeting(id, element) {
    Audio.stopAudio();

    state.selectedMeetingId = id;
    document.querySelectorAll('.meeting-item').forEach(el => el.classList.remove('active'));
    if (element) element.classList.add('active');

    document.getElementById('main-empty').style.display = 'none';
    document.getElementById('ask-view').style.display = 'none';
    document.getElementById('details-view').style.display = 'flex';
    document.querySelector('.header-meta').style.visibility = 'visible';

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

    state.audioReady = Audio.loadAudioForMeeting(meeting.id, !!meeting.audio_file);
    applyProgress(meeting.id);
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
        // The file's own date, so imported recordings keep their real chronology.
        date: new Date(file.lastModified || Date.now()).toISOString(),
        platform: "Upload",
        duration: await readMediaDuration(file),
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

/** Duration of an audio/video file in seconds, or 0 if the browser can't read it. */
function readMediaDuration(file) {
    return new Promise(resolve => {
        const url = URL.createObjectURL(file);
        const media = document.createElement('audio');
        const done = (duration) => {
            URL.revokeObjectURL(url);
            resolve(Number.isFinite(duration) ? duration : 0);
        };
        media.preload = 'metadata';
        media.onloadedmetadata = () => done(media.duration);
        media.onerror = () => done(0);
        media.src = url;
    });
}

function setupAsk() {
    document.getElementById('ask-open-btn').addEventListener('click', showAskView);
    document.getElementById('ask-form').addEventListener('submit', handleAsk);
    askInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            document.getElementById('ask-form').requestSubmit();
        }
    });
}

function showAskView() {
    Audio.stopAudio();
    document.getElementById('details-view').style.display = 'none';
    document.getElementById('main-empty').style.display = 'none';
    document.getElementById('ask-view').style.display = 'flex';

    currentTitle.textContent = 'Poser une question';
    currentTitle.contentEditable = 'false';
    document.querySelector('.header-meta').style.visibility = 'hidden';

    const meeting = state.selectedMeetingId ? state.meetingData : null;
    askScope.disabled = !meeting;
    if (!meeting) askScope.checked = false;
    document.getElementById('ask-scope-text').textContent = meeting
        ? `Seulement « ${meeting.title} »`
        : 'Seulement la réunion sélectionnée';

    if (state.askResult) Ask.renderAnswer(state.askResult, openCitation);
    askInput.focus();
}

async function handleAsk(event) {
    event.preventDefault();
    const query = askInput.value.trim();
    if (!query) return;

    const meetingIds = askScope.checked && state.selectedMeetingId ? [state.selectedMeetingId] : null;
    askSubmit.disabled = true;
    askSubmit.textContent = 'Recherche...';
    Ask.renderAskLoading();

    try {
        state.askResult = await API.askRag(query, meetingIds);
        Ask.renderAnswer(state.askResult, openCitation);
    } catch (err) {
        console.error(err);
        Ask.renderAskError(err.message);
    } finally {
        askSubmit.disabled = false;
        askSubmit.textContent = 'Demander';
    }
}

async function openCitation(citation) {
    const el = document.querySelector(`.meeting-item[data-id="${citation.meeting_id}"]`);
    await selectMeeting(citation.meeting_id, el);
    UI.focusSegments(citation.segment_ids?.length ? citation.segment_ids : [citation.segment_id]);
    await state.audioReady;
    Audio.seekToTime(citation.start_time, false);
}
