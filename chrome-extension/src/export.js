/**
 * Transcript export and copy functionality.
 */

import state from './state.js';

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

export function copyTranscript() {
    const text = getFormattedText();
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('btn-copy');
        btn.textContent = 'Copié !';
        setTimeout(() => btn.textContent = 'Copier', 1500);
    });
}

export function exportTranscript() {
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
