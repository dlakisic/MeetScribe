import { getApiUrl, getApiToken } from './config.js';

async function authFetch(url, options = {}) {
    const headers = options.headers || {};
    const token = getApiToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    options.headers = headers;
    return fetch(url, options);
}

export async function fetchMeetings({ limit = 50, offset = 0 } = {}) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/transcripts?limit=${limit}&offset=${offset}`, { method: "GET" });
        if (res.status === 401) return { meetings: [], unauthorized: true };
        if (!res.ok) throw new Error("Failed to fetch meetings");
        return await res.json();
    } catch (err) {
        console.error(err);
        return { meetings: [] };
    }
}

export async function fetchMeetingDetails(id) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/transcripts/${id}`);
        if (res.status === 401) throw new Error("Unauthorized");
        if (!res.ok) throw new Error("Failed to fetch details");
        return await res.json();
    } catch (err) {
        console.error(err);
        return null;
    }
}

export async function saveSegmentText(segmentId, newText) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/segments/${segmentId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText }),
        });
        if (!res.ok) console.error('Failed to save segment', res.status);
        return res.ok;
    } catch (err) {
        console.error('Error saving segment:', err);
        return false;
    }
}

export async function saveSpeakerRename(meetingId, oldName, newName) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/meetings/${meetingId}/speakers`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: oldName, new_name: newName }),
        });
        if (!res.ok) console.error('Failed to rename speaker', res.status);
        return res.ok;
    } catch (err) {
        console.error('Error renaming speaker:', err);
        return false;
    }
}

export async function saveMeetingTitle(meetingId, title) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/meetings/${meetingId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });
        if (!res.ok) console.error('Failed to save title', res.status);
        return res.ok;
    } catch (err) {
        console.error('Error saving title:', err);
        return false;
    }
}

export async function deleteMeeting(meetingId) {
    try {
        const res = await authFetch(`${getApiUrl()}/api/meetings/${meetingId}`, { method: 'DELETE' });
        return res.ok;
    } catch (err) {
        console.error('Error deleting meeting:', err);
        return false;
    }
}

export async function uploadMeetingAudio(formData) {
    const headers = {};
    const uploadToken = getApiToken();
    if (uploadToken) headers['Authorization'] = `Bearer ${uploadToken}`;

    const res = await fetch(`${getApiUrl()}/api/upload`, {
        method: 'POST',
        headers: headers,
        body: formData
    });

    if (res.status === 401) throw new Error('Non autorisé (vérifiez votre token)');
    if (!res.ok) throw new Error('Upload failed');
    return await res.json();
}

export async function fetchJobStatus(jobId) {
    const res = await authFetch(`${getApiUrl()}/api/status/${jobId}`);
    if (!res.ok) throw new Error('Failed to fetch job status');
    return await res.json();
}

export async function fetchAudioBlob(url) {
    const res = await authFetch(url);
    if (!res.ok) throw new Error('Audio not available');
    return res.blob();
}
