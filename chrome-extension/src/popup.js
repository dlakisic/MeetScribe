/**
 * MeetScribe Popup
 */

const statusText = document.getElementById('status-text');
const backendStatus = document.getElementById('backend-status');
const meetingInfo = document.getElementById('meeting-info');
const meetingTitle = document.getElementById('meeting-title');
const meetingDuration = document.getElementById('meeting-duration');
const meetingParticipants = document.getElementById('meeting-participants');
const toggleBtn = document.getElementById('toggle-btn');
const screenshotBtn = document.getElementById('screenshot-btn');

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
      statusText.textContent = 'Enregistrement...';
      statusText.className = 'status-value recording';

      meetingInfo.classList.remove('hidden');
      meetingTitle.textContent = response.meetingTitle || 'Meeting';

      const duration = Math.floor((Date.now() - response.startTime) / 1000);
      const minutes = Math.floor(duration / 60);
      const seconds = duration % 60;
      meetingDuration.textContent = `${minutes}:${seconds.toString().padStart(2, '0')} - ${response.screenshotCount} capture(s)`;

      // Show participants
      if (response.participants && response.participants.length > 0) {
        meetingParticipants.textContent = `Participants: ${response.participants.join(', ')}`;
      } else {
        meetingParticipants.textContent = '';
      }

      toggleBtn.textContent = "Arrêter l'enregistrement";
      toggleBtn.className = 'btn btn-danger';
      screenshotBtn.disabled = false;
    } else {
      statusText.textContent = 'Inactif';
      statusText.className = 'status-value idle';

      meetingInfo.classList.add('hidden');

      toggleBtn.textContent = "Démarrer l'enregistrement";
      toggleBtn.className = 'btn btn-primary';
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
      backendStatus.className = 'status-value connected';
    } else {
      throw new Error('Backend error');
    }
  } catch (error) {
    backendStatus.textContent = 'Hors ligne';
    backendStatus.className = 'status-value';
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
