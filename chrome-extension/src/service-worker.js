import * as Config from './config.js';

const PLATFORMS = {
  'meet.google.com': { name: 'Google Meet', priority: 0 },
  'zoom.us': { name: 'Zoom', priority: 0 },
  'teams.microsoft.com': { name: 'Microsoft Teams', priority: 1 },
};

const RecordingState = {
  IDLE: 'idle',
  STARTING: 'starting',
  RECORDING: 'recording',
  STOPPING: 'stopping',
};

let state = {
  recordingState: RecordingState.IDLE,
  currentTabId: null,
  currentPlatform: null,
  recordingStartTime: null,
  meetingTitle: null,
  meetingUrl: null,
  screenshots: [],
  participants: [],
  autoStartTimeout: null,
};

Config.loadConfig().then(() => {
  console.log('MeetScribe config loaded:', Config.getConfig());
});

chrome.runtime.onInstalled.addListener(() => {
  console.log('MeetScribe installed');
  Config.loadConfig();
});

function getAuthHeaders() {
  const headers = {};
  const token = Config.getApiToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function detectPlatform(url) {
  try {
    const urlObj = new URL(url);
    for (const [domain, info] of Object.entries(PLATFORMS)) {
      if (urlObj.hostname === domain || urlObj.hostname.endsWith('.' + domain)) {
        return { domain, ...info };
      }
    }
  } catch (e) {
    console.error('Invalid URL:', url);
  }
  return null;
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.status === 'complete') {
    handleTabUpdate(tabId, tab);
  }
});

async function handleTabUpdate(tabId, tab) {
  const platform = detectPlatform(tab.url);

  if (platform && state.recordingState === RecordingState.IDLE) {
    console.log(`Detected ${platform.name} meeting:`, tab.url);

    if (state.autoStartTimeout) {
      clearTimeout(state.autoStartTimeout);
    }

    state.autoStartTimeout = setTimeout(async () => {
      const currentTab = await chrome.tabs.get(tabId).catch(() => null);
      if (currentTab && detectPlatform(currentTab.url)) {
        await startRecording(tabId, currentTab, platform);
      }
    }, Config.getAutoStartDelay() * 1000);

    chrome.action.setBadgeText({ text: '...' });
    chrome.action.setBadgeBackgroundColor({ color: '#FFA500' });

  } else if (!platform && state.recordingState === RecordingState.RECORDING && tabId === state.currentTabId) {
    console.log('User left meeting page, stopping recording');
    await stopRecording();
  }
}

chrome.tabs.onRemoved.addListener((tabId) => {
  if (state.recordingState === RecordingState.RECORDING && tabId === state.currentTabId) {
    console.log('Meeting tab closed, stopping recording');
    stopRecording();
  }
});

async function startRecording(tabId, tab, platform) {
  if (state.recordingState !== RecordingState.IDLE) {
    console.log('Cannot start: state is', state.recordingState);
    return;
  }

  state.recordingState = RecordingState.STARTING;
  console.log('Starting recording for', platform.name);

  try {
    await setupOffscreenDocument();

    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId,
    });

    const meetingTitle = extractMeetingTitle(tab.title, platform);

    await chrome.runtime.sendMessage({
      type: 'START_RECORDING',
      target: 'offscreen',
      data: {
        streamId,
        tabId,
        meetingTitle,
      },
    });

    // All setup succeeded — commit state atomically
    state.currentTabId = tabId;
    state.currentPlatform = platform;
    state.meetingTitle = meetingTitle;
    state.meetingUrl = tab.url;
    state.screenshots = [];
    state.participants = [];
    state.recordingStartTime = Date.now();
    state.recordingState = RecordingState.RECORDING;

    chrome.action.setBadgeText({ text: 'REC' });
    chrome.action.setBadgeBackgroundColor({ color: '#FF0000' });

    chrome.tabs.sendMessage(tabId, { type: 'GET_PARTICIPANTS' })
      .then((response) => {
        if (response?.participants) {
          state.participants = response.participants;
          console.log('Initial participants:', state.participants);
        }
      })
      .catch(() => {});

    chrome.notifications.create({
      type: 'basic',
      iconUrl: 'icons/icon128.png',
      title: 'MeetScribe',
      message: `Enregistrement démarré: ${state.meetingTitle}`,
    });
  } catch (error) {
    console.error('Failed to start recording:', error);
    state.recordingState = RecordingState.IDLE;
    chrome.action.setBadgeText({ text: '' });
    await chrome.offscreen.closeDocument().catch(() => {});
  }
}

async function stopRecording() {
  if (state.recordingState !== RecordingState.RECORDING) {
    console.log('Cannot stop: state is', state.recordingState);
    return;
  }

  state.recordingState = RecordingState.STOPPING;
  console.log('Stopping recording');

  try {
    const response = await chrome.runtime.sendMessage({
      type: 'STOP_RECORDING',
      target: 'offscreen',
    });

    const duration = (Date.now() - state.recordingStartTime) / 1000;

    if (response && response.micBlob && response.tabBlob) {
      await uploadRecording(response.micBlob, response.tabBlob, duration);
    }
  } catch (error) {
    console.error('Error during stop recording:', error);
  } finally {
    state.recordingState = RecordingState.IDLE;
    state.currentTabId = null;
    state.currentPlatform = null;
    state.recordingStartTime = null;

    chrome.action.setBadgeText({ text: '' });
    await chrome.offscreen.closeDocument().catch(() => {});
  }
}

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
    const response = await fetch(`${Config.getApiUrl()}/api/upload`, {
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

function extractMeetingTitle(tabTitle, platform) {
  let title = tabTitle
    .replace(' - Google Meet', '')
    .replace(' | Microsoft Teams', '')
    .replace(' - Zoom', '')
    .trim();

  if (!title || title === 'Meet') {
    title = `${platform.name} - ${new Date().toLocaleDateString('fr-FR')}`;
  }

  return title;
}

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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'PARTICIPANTS_UPDATE') {
    if (sender.tab?.id && sender.tab.id === state.currentTabId) {
      handleParticipantsUpdate(message.data);
      sendResponse({ success: true });
    } else {
      sendResponse({ error: 'Ignored: not from active tab' });
    }
    return true;
  }

  if (message.target === 'service-worker') {
    handleMessage(message, sendResponse);
    return true;
  }
});

function handleParticipantsUpdate(data) {
  if (state.recordingState !== RecordingState.RECORDING) return;

  state.participants = data.participants || [];

  if (data.meetingTitle && data.meetingTitle !== 'Meet') {
    state.meetingTitle = data.meetingTitle;
  }

  console.log('Participants updated:', state.participants);
}

async function handleMessage(message, sendResponse) {
  switch (message.type) {
    case 'GET_STATE':
      sendResponse({
        isRecording: state.recordingState === RecordingState.RECORDING,
        platform: state.currentPlatform,
        startTime: state.recordingStartTime,
        meetingTitle: state.meetingTitle,
        screenshotCount: state.screenshots.length,
        participants: state.participants,
      });
      break;

    case 'TOGGLE_RECORDING':
      if (state.recordingState === RecordingState.RECORDING) {
        await stopRecording();
      } else if (state.recordingState === RecordingState.IDLE) {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const platform = detectPlatform(tab.url);
        if (platform) {
          await startRecording(tab.id, tab, platform);
        }
      }
      sendResponse({ isRecording: state.recordingState === RecordingState.RECORDING });
      break;

    case 'TAKE_SCREENSHOT':
      await takeScreenshot();
      sendResponse({ count: state.screenshots.length });
      break;

    case 'UPDATE_CONFIG':
      if (message.data) {
        await Config.saveConfig(message.data);
      }
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: 'Unknown message type' });
  }
}

async function takeScreenshot() {
  if (state.recordingState !== RecordingState.RECORDING || !state.currentTabId) {
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

    if (state.screenshots.length > Config.getMaxScreenshots()) {
      state.screenshots.shift();
    }

    chrome.action.setBadgeText({ text: `${state.screenshots.length}` });

    chrome.tabs.sendMessage(state.currentTabId, { type: 'SCREENSHOT_FLASH' }).catch(() => {});

    console.log(`Screenshot taken (${state.screenshots.length} total)`);
  } catch (error) {
    console.error('Screenshot error:', error);
  }
}

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
