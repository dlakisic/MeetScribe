/**
 * Job status polling for transcription progress.
 */

import * as API from './api.js';
import state from './state.js';

export function startStatusPolling(jobId, meetingId, { loadMeetings, selectMeeting }) {
    const uploadBtn = document.getElementById('upload-btn');
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
