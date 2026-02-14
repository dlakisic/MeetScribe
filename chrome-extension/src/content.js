/**
 * MeetScribe Content Script
 * Extracts participant names and meeting info from the page
 */

// Platform-specific selectors
const SELECTORS = {
  'meet.google.com': {
    // Participant names in video tiles
    participantNames: '[data-self-name]',
    // Names in the participant list panel
    participantList: '[role="listitem"] [data-participant-id]',
    // Meeting title from the page
    meetingTitle: '[data-meeting-title]',
    // Self name
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

// Detect platform
function detectPlatform() {
  const hostname = window.location.hostname;
  for (const domain of Object.keys(SELECTORS)) {
    if (hostname.includes(domain)) {
      return domain;
    }
  }
  return null;
}

// Extract participants from Google Meet
function extractGoogleMeetParticipants() {
  const participants = new Set();

  // Method 1: Video tile names (most reliable)
  document.querySelectorAll('[data-self-name]').forEach((el) => {
    const name = el.textContent?.trim();
    if (name && name.length > 0) {
      participants.add(name);
    }
  });

  // Method 2: Participant list (if panel is open)
  document.querySelectorAll('[role="listitem"]').forEach((el) => {
    // Look for the name element within the list item
    const nameEl = el.querySelector('[data-participant-id]');
    if (nameEl) {
      const name = nameEl.textContent?.trim();
      if (name && name.length > 0) {
        participants.add(name);
      }
    }
  });

  // Method 3: aria-label on video containers (e.g., "Name's camera")
  document.querySelectorAll('[aria-label*="camera"]').forEach((el) => {
    const label = el.getAttribute('aria-label');
    if (label) {
      // Extract name from "Name's camera" pattern
      const match = label.match(/^(.+?)(?:'s|) camera/i);
      if (match) {
        participants.add(match[1].trim());
      }
    }
  });

  return Array.from(participants);
}

// Extract participants from Zoom
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

// Extract participants from Teams
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

// Main extraction function
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

// Extract meeting title
function extractMeetingTitle() {
  if (currentPlatform === 'meet.google.com') {
    // Try multiple methods for Google Meet
    const titleEl = document.querySelector('[data-meeting-title]');
    if (titleEl) return titleEl.textContent?.trim();

    // From page title
    const pageTitle = document.title.replace(' - Google Meet', '').trim();
    if (pageTitle && pageTitle !== 'Meet') return pageTitle;

    // From URL (meeting code)
    const match = window.location.pathname.match(/\/([a-z]{3}-[a-z]{4}-[a-z]{3})/);
    if (match) return `Meeting ${match[1]}`;
  }

  return document.title;
}

// Send participants to service worker
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
    }).catch(() => {
      // Service worker might not be ready
    });

    console.log('[MeetScribe] Participants:', participants);
  }
}

// Set up mutation observer to detect participant changes
function setupObserver() {
  if (observer) {
    observer.disconnect();
  }

  observer = new MutationObserver((mutations) => {
    // Debounce updates
    clearTimeout(window._meetscribeDebounce);
    window._meetscribeDebounce = setTimeout(sendParticipants, 500);
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });
}

// Handle screenshot flash effect
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

// Listen for messages from service worker
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

// Initialize
function init() {
  currentPlatform = detectPlatform();

  if (!currentPlatform) {
    console.log('[MeetScribe] Not a supported meeting platform');
    return;
  }

  console.log('[MeetScribe] Detected platform:', currentPlatform);

  // Initial extraction after page settles
  setTimeout(() => {
    sendParticipants();
    setupObserver();
  }, 2000);

  // Periodic extraction (backup)
  setInterval(sendParticipants, 10000);
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
