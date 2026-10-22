/**
 * Job status polling for transcription progress.
 *
 * Progress shows on the meeting in the sidebar (and in its transcript while it
 * is open), and polling resumes for jobs still running after a page reload.
 */

import * as API from './api.js';
import state from './state.js';

const POLL_INTERVAL_MS = 3000;

const STEP_LABELS = {
    sending: 'Envoi au GPU',
    transcribing_mic: 'Transcription du micro',
    transcribing_tab: 'Transcription',
    diarizing: 'Séparation des voix',
    merging: 'Assemblage',
    saving: 'Assemblage',
    extracting: 'Résumé',
};

function progressLabel(job) {
    const label = STEP_LABELS[job.progress_step]
        || (job.status === 'queued' ? 'En attente' : 'Démarrage');
    return job.progress_percent != null ? `${label} · ${job.progress_percent} %` : label;
}

/** Reflect a meeting's known progress in the sidebar and the open transcript. */
export function applyProgress(meetingId) {
    const progress = state.jobProgress.get(meetingId);
    if (!progress) return;

    const item = document.querySelector(`.meeting-item[data-id="${meetingId}"]`);
    if (item) {
        const badge = item.querySelector('.status-badge');
        if (badge) badge.textContent = progress.label;

        let bar = item.querySelector('.meeting-progress');
        if (!bar) {
            bar = document.createElement('div');
            bar.className = 'meeting-progress';
            bar.innerHTML = '<div class="meeting-progress-fill"></div>';
            item.appendChild(bar);
        }
        const fill = bar.querySelector('.meeting-progress-fill');
        bar.classList.toggle('indeterminate', progress.percent == null);
        fill.style.width = progress.percent == null ? '' : `${progress.percent}%`;
    }

    if (state.selectedMeetingId === meetingId && !state.transcriptData) {
        const container = document.getElementById('transcript-container');
        container.innerHTML = '';
        const placeholder = document.createElement('div');
        placeholder.className = 'empty-state';
        placeholder.textContent = `Traitement en cours : ${progress.label}`;
        container.appendChild(placeholder);
    }
}

export function applyAllProgress() {
    for (const meetingId of state.jobProgress.keys()) applyProgress(meetingId);
}

/**
 * Poll a job until it finishes. autoSelect opens the meeting when done, which
 * suits a file the user just imported but not jobs resumed after a reload.
 */
export function startStatusPolling(jobId, meetingId, { loadMeetings, selectMeeting, autoSelect = true }) {
    if (state.pollTimers.has(jobId)) return;

    const finish = async () => {
        clearInterval(state.pollTimers.get(jobId));
        state.pollTimers.delete(jobId);
        state.jobProgress.delete(meetingId);
        await loadMeetings();
    };

    const tick = async () => {
        try {
            const job = await API.fetchJobStatus(jobId);

            if (job.status === 'completed') {
                await finish();
                if (autoSelect) {
                    const el = document.querySelector(`.meeting-item[data-id="${meetingId}"]`);
                    selectMeeting(meetingId, el);
                }
            } else if (job.status === 'failed') {
                await finish();
                alert('La transcription a échoué : ' + (job.error || 'erreur inconnue'));
            } else {
                state.jobProgress.set(meetingId, {
                    label: progressLabel(job),
                    percent: job.progress_percent,
                });
                applyProgress(meetingId);
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    };

    state.pollTimers.set(jobId, setInterval(tick, POLL_INTERVAL_MS));
    tick();
}

/** Resume polling for jobs that were already running when the page loaded. */
export async function resumeActiveJobs(callbacks) {
    try {
        const jobs = await API.fetchActiveJobs();
        jobs.forEach(job => startStatusPolling(job.job_id, job.meeting_id, { ...callbacks, autoSelect: false }));
    } catch (err) {
        console.error('Could not resume job polling:', err);
    }
}
