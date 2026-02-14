/**
 * MeetScribe Service Worker
 * Handles URL detection, recording coordination, and backend communication
 */

// Configuration
const CONFIG = {
  backendUrl: 'http://192.168.1.19:8888',
  apiToken: null, // Optional: Bearer token for API auth
  autoStartDelay: 5000, // Wait 5s before auto-starting recording
  platforms: {
    'meet.google.com': { name: 'Google Meet', priority: 0 },
    'zoom.us': { name: 'Zoom', priority: 0 },
    'teams.microsoft.com': { name: 'Microsoft Teams', priority: 1 },
  },
};

// State
let state = {
  isRecording: false,
  currentTabId: null,
  currentPlatform: null,
  recordingStartTime: null,
  meetingTitle: null,
  meetingUrl: null,
  screenshots: [],
  participants: [],
  autoStartTimeout: null,
};

// Initialize
chrome.runtime.onInstalled.addListener(() => {
  console.log('MeetScribe installed');
  loadConfig();
});

// Load config from storage
async function loadConfig() {
  const stored = await chrome.storage.local.get(['backendUrl', 'apiToken']);
  if (stored.backendUrl) {
    CONFIG.backendUrl = stored.backendUrl;
  }
  if (stored.apiToken) {
    CONFIG.apiToken = stored.apiToken;
  }
}

// Save config to storage
async function saveConfig() {
  await chrome.storage.local.set({
    backendUrl: CONFIG.backendUrl,
    apiToken: CONFIG.apiToken,
  });
}

// Helper to build fetch headers with optional auth
function getAuthHeaders() {
  const headers = {};
  if (CONFIG.apiToken) {
    headers['Authorization'] = `Bearer ${CONFIG.apiToken}`;
  }
  return headers;
}

// Check if URL matches a meeting platform
function detectPlatform(url) {
  try {
    const urlObj = new URL(url);
    for (const [domain, info] of Object.entries(CONFIG.platforms)) {
      if (urlObj.hostname.includes(domain)) {
        return { domain, ...info };
      }
    }
  } catch (e) {
    console.error('Invalid URL:', url);
  }
  return null;
}

// Tab URL change listener
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.status === 'complete') {
    handleTabUpdate(tabId, tab);
  }
});

// Handle tab updates
async function handleTabUpdate(tabId, tab) {
  const platform = detectPlatform(tab.url);

  if (platform && !state.isRecording) {
    console.log(`Detected ${platform.name} meeting:`, tab.url);

    // Clear any existing auto-start timeout
    if (state.autoStartTimeout) {
      clearTimeout(state.autoStartTimeout);
    }

    // Set up auto-start
    state.autoStartTimeout = setTimeout(async () => {
      // Re-check if we should start (user might have navigated away)
      const currentTab = await chrome.tabs.get(tabId).catch(() => null);
      if (currentTab && detectPlatform(currentTab.url)) {
        await startRecording(tabId, currentTab, platform);
      }
    }, CONFIG.autoStartDelay);

    // Update badge to show pending
    chrome.action.setBadgeText({ text: '...' });
    chrome.action.setBadgeBackgroundColor({ color: '#FFA500' });

  } else if (!platform && state.isRecording && tabId === state.currentTabId) {
    // User left the meeting page
    console.log('User left meeting page, stopping recording');
    await stopRecording();
  }
}

// Tab closed listener
chrome.tabs.onRemoved.addListener((tabId) => {
  if (state.isRecording && tabId === state.currentTabId) {
    console.log('Meeting tab closed, stopping recording');
    stopRecording();
  }
});

// Start recording
async function startRecording(tabId, tab, platform) {
  if (state.isRecording) {
    console.log('Already recording');
    return;
  }

  console.log('Starting recording for', platform.name);

  state.isRecording = true;
  state.currentTabId = tabId;
  state.currentPlatform = platform;
  state.recordingStartTime = Date.now();
  state.meetingTitle = extractMeetingTitle(tab.title, platform);
  state.meetingUrl = tab.url;
  state.screenshots = [];
  state.participants = [];

  // Request initial participants from content script
  chrome.tabs.sendMessage(tabId, { type: 'GET_PARTICIPANTS' })
    .then((response) => {
      if (response?.participants) {
        state.participants = response.participants;
        console.log('Initial participants:', state.participants);
      }
    })
    .catch(() => {});

  // Update badge
  chrome.action.setBadgeText({ text: 'REC' });
  chrome.action.setBadgeBackgroundColor({ color: '#FF0000' });

  // Create offscreen document for recording
  await setupOffscreenDocument();

  // Start capturing tab audio
  const streamId = await chrome.tabCapture.getMediaStreamId({
    targetTabId: tabId,
  });

  // Send to offscreen document to start recording
  await chrome.runtime.sendMessage({
    type: 'START_RECORDING',
    target: 'offscreen',
    data: {
      streamId,
      tabId,
      meetingTitle: state.meetingTitle,
    },
  });

  // Show notification
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title: 'MeetScribe',
    message: `Enregistrement démarré: ${state.meetingTitle}`,
  });
}

// Stop recording
async function stopRecording() {
  if (!state.isRecording) {
    console.log('Not recording');
    return;
  }

  console.log('Stopping recording');

  // Tell offscreen document to stop and get the recordings
  const response = await chrome.runtime.sendMessage({
    type: 'STOP_RECORDING',
    target: 'offscreen',
  });

  // Clear badge
  chrome.action.setBadgeText({ text: '' });

  const duration = (Date.now() - state.recordingStartTime) / 1000;

  // Upload to backend
  if (response && response.micBlob && response.tabBlob) {
    await uploadRecording(response.micBlob, response.tabBlob, duration);
  }

  // Reset state
  state.isRecording = false;
  state.currentTabId = null;
  state.currentPlatform = null;
  state.recordingStartTime = null;

  // Close offscreen document
  await chrome.offscreen.closeDocument().catch(() => {});
}

// Upload recording to backend
async function uploadRecording(micBlob, tabBlob, duration) {
  console.log('Uploading recording to backend...');

  const formData = new FormData();
  formData.append('mic_file', micBlob, 'mic.webm');
  formData.append('tab_file', tabBlob, 'tab.webm');
  formData.append('metadata', JSON.stringify({
    title: state.meetingTitle,
    date: new Date().toISOString(),
    duration: duration,
    platform: state.currentPlatform?.name,
    url: state.meetingUrl,
    participants: state.participants,
  }));

  try {
    const response = await fetch(`${CONFIG.backendUrl}/api/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });

    if (response.ok) {
      const result = await response.json();
      console.log('Upload successful:', result);

      chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: 'MeetScribe',
        message: `Enregistrement uploadé! Job: ${result.job_id}`,
      });
    } else {
      throw new Error(`Upload failed: ${response.status}`);
    }
  } catch (error) {
    console.error('Upload error:', error);

    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: 'MeetScribe - Erreur',
      message: `Échec de l'upload: ${error.message}`,
    });
  }
}

// Extract meeting title from tab title
function extractMeetingTitle(tabTitle, platform) {
  // Remove common suffixes
  let title = tabTitle
    .replace(' - Google Meet', '')
    .replace(' | Microsoft Teams', '')
    .replace(' - Zoom', '')
    .trim();

  // Default title if empty
  if (!title || title === 'Meet') {
    title = `${platform.name} - ${new Date().toLocaleDateString('fr-FR')}`;
  }

  return title;
}

// Setup offscreen document for audio capture
async function setupOffscreenDocument() {
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
  });

  if (existingContexts.length > 0) {
    return;
  }

  await chrome.offscreen.createDocument({
    url: 'src/offscreen.html',
    reasons: ['USER_MEDIA', 'DISPLAY_MEDIA'],
    justification: 'Recording meeting audio',
  });
}

// Handle messages from popup, offscreen, and content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Handle participant updates from content script
  if (message.type === 'PARTICIPANTS_UPDATE') {
    handleParticipantsUpdate(message.data);
    sendResponse({ success: true });
    return true;
  }

  if (message.target === 'service-worker') {
    handleMessage(message, sendResponse);
    return true; // Keep channel open for async response
  }
});

// Handle participant updates from content script
function handleParticipantsUpdate(data) {
  if (!state.isRecording) return;

  state.participants = data.participants || [];

  // Update meeting title if we got a better one
  if (data.meetingTitle && data.meetingTitle !== 'Meet') {
    state.meetingTitle = data.meetingTitle;
  }

  console.log('Participants updated:', state.participants);
}

async function handleMessage(message, sendResponse) {
  switch (message.type) {
    case 'GET_STATE':
      sendResponse({
        isRecording: state.isRecording,
        platform: state.currentPlatform,
        startTime: state.recordingStartTime,
        meetingTitle: state.meetingTitle,
        screenshotCount: state.screenshots.length,
        participants: state.participants,
      });
      break;

    case 'TOGGLE_RECORDING':
      if (state.isRecording) {
        await stopRecording();
      } else {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const platform = detectPlatform(tab.url);
        if (platform) {
          await startRecording(tab.id, tab, platform);
        }
      }
      sendResponse({ isRecording: state.isRecording });
      break;

    case 'TAKE_SCREENSHOT':
      await takeScreenshot();
      sendResponse({ count: state.screenshots.length });
      break;

    case 'UPDATE_CONFIG':
      if (message.data.backendUrl) {
        CONFIG.backendUrl = message.data.backendUrl;
        await saveConfig();
      }
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: 'Unknown message type' });
  }
}

// Take screenshot of current tab
async function takeScreenshot() {
  if (!state.isRecording || !state.currentTabId) {
    console.log('Cannot take screenshot: not recording');
    return;
  }

  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, {
      format: 'png',
    });

    state.screenshots.push({
      timestamp: Date.now() - state.recordingStartTime,
      dataUrl,
    });

    // Update badge to show screenshot count
    chrome.action.setBadgeText({ text: `${state.screenshots.length}` });

    // Flash effect (via content script)
    chrome.tabs.sendMessage(state.currentTabId, { type: 'SCREENSHOT_FLASH' }).catch(() => {});

    console.log(`Screenshot taken (${state.screenshots.length} total)`);
  } catch (error) {
    console.error('Screenshot error:', error);
  }
}

// Handle keyboard commands
chrome.commands.onCommand.addListener((command) => {
  switch (command) {
    case 'take-screenshot':
      takeScreenshot();
      break;
    case 'toggle-recording':
      handleMessage({ type: 'TOGGLE_RECORDING' }, () => {});
      break;
  }
});
