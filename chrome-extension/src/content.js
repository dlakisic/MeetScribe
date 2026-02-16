const SELECTORS = {
  'meet.google.com': {
    participantNames: '[data-self-name]',
    participantList: '[role="listitem"] [data-participant-id]',
    meetingTitle: '[data-meeting-title]',
    selfName: '[data-self-name="true"]',
  },
  'zoom.us': {
    participantNames: '.participants-item__display-name',
    participantList: '.participants-ul .participants-item',
    meetingTitle: '.meeting-info-topic',
  },
  'teams.microsoft.com': {
    participantNames: '[data-tid="roster-participant"]',
    participantList: '[data-tid="roster-list"] [role="listitem"]',
    meetingTitle: '[data-tid="meeting-title"]',
  },
};

let currentPlatform = null;
let participantsCache = new Set();
let observer = null;

function detectPlatform() {
  const hostname = window.location.hostname;
  for (const domain of Object.keys(SELECTORS)) {
    if (hostname === domain || hostname.endsWith('.' + domain)) {
      return domain;
    }
  }
  return null;
}

function extractGoogleMeetParticipants() {
  const participants = new Set();

  document.querySelectorAll('[data-self-name]').forEach((el) => {
    const name = el.textContent?.trim();
    if (name && name.length > 0) {
      participants.add(name);
    }
  });

  document.querySelectorAll('[role="listitem"]').forEach((el) => {
    const nameEl = el.querySelector('[data-participant-id]');
    if (nameEl) {
      const name = nameEl.textContent?.trim();
      if (name && name.length > 0) {
        participants.add(name);
      }
    }
  });

  document.querySelectorAll('[aria-label*="camera"]').forEach((el) => {
    const label = el.getAttribute('aria-label');
    if (label) {
      const match = label.match(/^(.+?)(?:'s|) camera/i);
      if (match) {
        participants.add(match[1].trim());
      }
    }
  });

  return Array.from(participants);
}

function extractZoomParticipants() {
  const participants = new Set();

  document.querySelectorAll('.participants-item__display-name').forEach((el) => {
    const name = el.textContent?.trim();
    if (name) {
      participants.add(name);
    }
  });

  return Array.from(participants);
}

function extractTeamsParticipants() {
  const participants = new Set();

  document.querySelectorAll('[data-tid="roster-participant"]').forEach((el) => {
    const name = el.textContent?.trim();
    if (name) {
      participants.add(name);
    }
  });

  return Array.from(participants);
}

function extractParticipants() {
  switch (currentPlatform) {
    case 'meet.google.com':
      return extractGoogleMeetParticipants();
    case 'zoom.us':
      return extractZoomParticipants();
    case 'teams.microsoft.com':
      return extractTeamsParticipants();
    default:
      return [];
  }
}

function extractMeetingTitle() {
  if (currentPlatform === 'meet.google.com') {
    const titleEl = document.querySelector('[data-meeting-title]');
    if (titleEl) return titleEl.textContent?.trim();

    const pageTitle = document.title.replace(' - Google Meet', '').trim();
    if (pageTitle && pageTitle !== 'Meet') return pageTitle;

    const match = window.location.pathname.match(/\/([a-z]{3}-[a-z]{4}-[a-z]{3})/);
    if (match) return `Meeting ${match[1]}`;
  }

  return document.title;
}

function sendParticipants() {
  const participants = extractParticipants();
  const newParticipants = participants.filter((p) => !participantsCache.has(p));

  if (newParticipants.length > 0 || participants.length !== participantsCache.size) {
    participantsCache = new Set(participants);

    chrome.runtime.sendMessage({
      type: 'PARTICIPANTS_UPDATE',
      target: 'service-worker',
      data: {
        participants,
        meetingTitle: extractMeetingTitle(),
        platform: currentPlatform,
        url: window.location.href,
      },
    }).catch(() => {});

    console.log('[MeetScribe] Participants:', participants);
  }
}

function setupObserver() {
  if (observer) {
    observer.disconnect();
  }

  observer = new MutationObserver((mutations) => {
    clearTimeout(window._meetscribeDebounce);
    window._meetscribeDebounce = setTimeout(sendParticipants, 500);
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}

function flashScreen() {
  const flash = document.createElement('div');
  flash.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: white;
    opacity: 0.7;
    z-index: 999999;
    pointer-events: none;
    transition: opacity 0.3s;
  `;
  document.body.appendChild(flash);

  requestAnimationFrame(() => {
    flash.style.opacity = '0';
    setTimeout(() => flash.remove(), 300);
  });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'GET_PARTICIPANTS':
      sendResponse({
        participants: extractParticipants(),
        meetingTitle: extractMeetingTitle(),
      });
      break;

    case 'SCREENSHOT_FLASH':
      flashScreen();
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: 'Unknown message type' });
  }
  return true;
});

function init() {
  currentPlatform = detectPlatform();

  if (!currentPlatform) {
    console.log('[MeetScribe] Not a supported meeting platform');
    return;
  }

  console.log('[MeetScribe] Detected platform:', currentPlatform);

  setTimeout(() => {
    sendParticipants();
    setupObserver();
  }, 2000);

  setInterval(sendParticipants, 10000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
