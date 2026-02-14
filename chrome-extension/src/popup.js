/**
 * MeetScribe Popup
 */

const statusText = document.getElementById('status-text');
const backendStatus = document.getElementById('backend-status');
const durationDisplay = document.getElementById('duration-display');
const captureCount = document.getElementById('capture-count');
const meetingInfo = document.getElementById('meeting-info');
const meetingTitle = document.getElementById('meeting-title');
const meetingPlatform = document.getElementById('meeting-platform');
const meetingParticipants = document.getElementById('meeting-participants');
const toggleBtn = document.getElementById('toggle-btn');
const screenshotBtn = document.getElementById('screenshot-btn');
const dashboardBtn = document.getElementById('dashboard-btn');

let updateInterval = null;

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await updateState();
  await checkBackend();

  // Update state every second
  updateInterval = setInterval(updateState, 1000);
});

// Clean up on close
window.addEventListener('unload', () => {
  if (updateInterval) {
    clearInterval(updateInterval);
  }
});

// Update UI from service worker state
async function updateState() {
  try {
    const response = await chrome.runtime.sendMessage({
      type: 'GET_STATE',
      target: 'service-worker',
    });

    if (response.isRecording) {
      statusText.textContent = 'REC';
      statusText.className = 'meter-value live';

      const duration = Math.floor((Date.now() - response.startTime) / 1000);
      const minutes = Math.floor(duration / 60);
      const seconds = duration % 60;
      durationDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      durationDisplay.className = 'meter-value live';

      captureCount.textContent = response.screenshotCount || 0;

      meetingInfo.classList.remove('hidden');
      meetingTitle.textContent = response.meetingTitle || 'Meeting';

      if (response.currentPlatform) {
        meetingPlatform.textContent = response.currentPlatform;
      }

      // Show participants
      if (response.participants && response.participants.length > 0) {
        meetingParticipants.textContent = response.participants.join(', ');
        meetingParticipants.classList.remove('hidden');
      } else {
        meetingParticipants.classList.add('hidden');
      }

      toggleBtn.querySelector('.label').textContent = 'STOP';
      toggleBtn.classList.add('armed');
      screenshotBtn.disabled = false;
    } else {
      statusText.textContent = 'STANDBY';
      statusText.className = 'meter-value standby';

      durationDisplay.textContent = '--:--';
      durationDisplay.className = 'meter-value';

      captureCount.textContent = '0';
      meetingInfo.classList.add('hidden');

      toggleBtn.querySelector('.label').textContent = 'ENREGISTRER';
      toggleBtn.classList.remove('armed');
      screenshotBtn.disabled = true;
    }
  } catch (error) {
    console.error('Failed to get state:', error);
  }
}

// Check backend connectivity
async function checkBackend() {
  try {
    const config = await chrome.storage.local.get(['backendUrl']);
    const backendUrl = config.backendUrl || 'http://192.168.1.19:8888';

    const response = await fetch(`${backendUrl}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });

    if (response.ok) {
      const data = await response.json();
      backendStatus.textContent = data.gpu_available ? 'GPU' : 'CPU';
      backendStatus.classList.add('connected');
      backendStatus.classList.remove('offline');
    } else {
      throw new Error('Backend error');
    }
  } catch (error) {
    backendStatus.textContent = 'OFFLINE';
    backendStatus.classList.add('offline');
    backendStatus.classList.remove('connected');
  }
}

// Toggle recording
toggleBtn.addEventListener('click', async () => {
  toggleBtn.disabled = true;

  try {
    await chrome.runtime.sendMessage({
      type: 'TOGGLE_RECORDING',
      target: 'service-worker',
    });
    await updateState();
  } catch (error) {
    console.error('Toggle failed:', error);
  }

  toggleBtn.disabled = false;
});

// Take screenshot
screenshotBtn.addEventListener('click', async () => {
  screenshotBtn.disabled = true;

  try {
    await chrome.runtime.sendMessage({
      type: 'TAKE_SCREENSHOT',
      target: 'service-worker',
    });
    await updateState();
  } catch (error) {
    console.error('Screenshot failed:', error);
  }

  screenshotBtn.disabled = false;
});

// Dashboard button
if (dashboardBtn) {
  dashboardBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'src/main.html' });
  });
}
