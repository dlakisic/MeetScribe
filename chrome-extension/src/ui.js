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

export function resetSpeakerColors() {
    speakerColorMap.clear();
    speakerColorIndex = 0;
}

// --- Rendering ---

export function renderMeetingList(meetings, selectedId, onSelect) {
    const meetingList = document.getElementById('meeting-list');
    meetingList.innerHTML = '';

    if (meetings.length === 0) {
        meetingList.innerHTML = '<div class="empty-state">Aucune réunion</div>';
        return;
    }

    meetings.forEach(meeting => {
        const el = document.createElement('div');
        el.className = 'meeting-item';
        el.dataset.id = meeting.id;
        if (meeting.id === selectedId) el.classList.add('active');
        el.onclick = () => onSelect(meeting.id, el);

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

export function renderTranscript(transcriptData, onSeek, onTextChange, onRename) {
    const transcriptContainer = document.getElementById('transcript-container');
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
            onSeek(startTime);
        });

        // Save on blur
        const textEl = el.querySelector('.segment-text');
        textEl.addEventListener('blur', () => {
            const newText = textEl.textContent.trim();
            if (newText !== seg.text && seg.id) {
                onTextChange(seg.id, newText, seg);
            }
        });

        // Rename speaker on click
        const speakerEl = el.querySelector('.segment-speaker');
        speakerEl.style.cursor = 'pointer';
        speakerEl.title = 'Cliquer pour renommer ce speaker';

        speakerEl.addEventListener('click', () => {
            onRename(seg.speaker);
        });

        transcriptContainer.appendChild(el);
    });
}

export function renderInsights(extractedData) {
    const summaryText = document.getElementById('summary-text');
    const actionsList = document.getElementById('actions-list');
    const decisionsList = document.getElementById('decisions-list');

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

export function highlightCurrentSegment(currentTime) {
    const transcriptContainer = document.getElementById('transcript-container');
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

export function clearSegmentHighlight() {
    document.querySelectorAll('.transcript-segment.playing')
        .forEach(el => el.classList.remove('playing'));
}
