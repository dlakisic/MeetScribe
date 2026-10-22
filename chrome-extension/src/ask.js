/**
 * Ask view: question form and RAG answer with clickable citations.
 */

import { escapeHtml } from './ui.js';

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

export function renderAskLoading() {
    document.getElementById('ask-result').innerHTML =
        '<div class="empty-state ask-hint"><p>Recherche dans les transcripts…</p></div>';
}

export function renderAskError(message) {
    document.getElementById('ask-result').innerHTML =
        `<div class="ask-error">${escapeHtml(message)}</div>`;
}

/**
 * Render an answer. [n] markers in the text become links to citation n.
 * onOpenCitation(citation) is called when a citation card is clicked.
 */
export function renderAnswer(result, onOpenCitation) {
    const container = document.getElementById('ask-result');
    container.innerHTML = '';
    const citations = result.citations || [];

    const answerCard = document.createElement('div');
    answerCard.className = 'insight-card ask-answer';
    const answerHtml = escapeHtml(result.answer).replace(/\[(\d+)\]/g, (match, n) =>
        Number(n) >= 1 && Number(n) <= citations.length
            ? `<button type="button" class="cite-ref" data-cite="${n}">${n}</button>`
            : match
    );
    answerCard.innerHTML = `
      <div class="insight-title">Réponse
        ${result.fallback_used
            ? '<span class="ask-badge" title="Le LLM est indisponible : voici le passage le plus pertinent.">sans LLM</span>'
            : ''}
      </div>
      <p class="ask-answer-text">${answerHtml}</p>
    `;
    answerCard.querySelectorAll('.cite-ref').forEach(btn => {
        btn.addEventListener('click', () => {
            const card = document.getElementById(`cite-${btn.dataset.cite}`);
            if (!card) return;
            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            card.classList.remove('flash');
            void card.offsetWidth; // restart the animation
            card.classList.add('flash');
        });
    });
    container.appendChild(answerCard);

    if (citations.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'summary-text';
        empty.textContent = 'Aucun passage cité.';
        container.appendChild(empty);
        return;
    }

    const title = document.createElement('div');
    title.className = 'ask-sources-title';
    title.textContent = `Sources (${citations.length})`;
    container.appendChild(title);

    citations.forEach((c, i) => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'citation-card';
        card.id = `cite-${i + 1}`;
        card.title = 'Ouvrir le transcript à ce passage';

        const date = c.meeting_date ? new Date(c.meeting_date).toLocaleDateString() : '';
        const lines = c.text.split('\n').map(line => {
            const sep = line.indexOf(': ');
            if (sep === -1) return `<div class="citation-line">${escapeHtml(line)}</div>`;
            return `<div class="citation-line"><span class="citation-speaker">${escapeHtml(line.slice(0, sep))}</span> ${escapeHtml(line.slice(sep + 2))}</div>`;
        }).join('');

        card.innerHTML = `
          <div class="citation-head">
            <span class="citation-number">${i + 1}</span>
            <span class="citation-meeting">${escapeHtml(c.meeting_title || `Réunion ${c.meeting_id}`)}</span>
            <span class="citation-meta">${escapeHtml(date)} · ${formatTime(c.start_time)}</span>
          </div>
          <div class="citation-text">${lines}</div>
        `;
        card.addEventListener('click', () => onOpenCitation(c));
        container.appendChild(card);
    });
}
