let micRecorder = null;
let tabRecorder = null;
let micChunks = [];
let tabChunks = [];
let micStream = null;
let tabStream = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target !== 'offscreen') {
    return;
  }

  switch (message.type) {
    case 'START_RECORDING':
      startRecording(message.data)
        .then(() => sendResponse({ success: true }))
        .catch((error) => sendResponse({ error: error.message }));
      return true;

    case 'STOP_RECORDING':
      stopRecording()
        .then((result) => sendResponse(result))
        .catch((error) => sendResponse({ error: error.message }));
      return true;
  }
});

async function startRecording({ streamId, tabId, meetingTitle }) {
  console.log('Offscreen: Starting recording');

  micChunks = [];
  tabChunks = [];

  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });
    console.log('Microphone stream acquired');
  } catch (error) {
    console.error('Failed to get microphone:', error);
    throw new Error('Microphone access denied');
  }

  try {
    tabStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    });
    console.log('Tab audio stream acquired');
  } catch (error) {
    console.error('Failed to get tab audio:', error);
    micStream?.getTracks().forEach((t) => t.stop());
    throw new Error('Tab audio capture failed');
  }

  const mimeType = 'audio/webm;codecs=opus';

  micRecorder = new MediaRecorder(micStream, { mimeType });
  tabRecorder = new MediaRecorder(tabStream, { mimeType });

  micRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) {
      micChunks.push(e.data);
    }
  };

  tabRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) {
      tabChunks.push(e.data);
    }
  };

  micRecorder.onerror = (e) => console.error('Mic recorder error:', e);
  tabRecorder.onerror = (e) => console.error('Tab recorder error:', e);

  micRecorder.start(1000);
  tabRecorder.start(1000);

  console.log('Recording started');
}

async function stopRecording() {
  console.log('Offscreen: Stopping recording');

  return new Promise((resolve, reject) => {
    let micStopped = false;
    let tabStopped = false;

    const checkComplete = () => {
      if (micStopped && tabStopped) {
        const micBlob = new Blob(micChunks, { type: 'audio/webm' });
        const tabBlob = new Blob(tabChunks, { type: 'audio/webm' });

        console.log(`Mic recording: ${micBlob.size} bytes`);
        console.log(`Tab recording: ${tabBlob.size} bytes`);

        micStream?.getTracks().forEach((t) => t.stop());
        tabStream?.getTracks().forEach((t) => t.stop());

        micRecorder = null;
        tabRecorder = null;
        micStream = null;
        tabStream = null;

        resolve({ micBlob, tabBlob });
      }
    };

    if (micRecorder && micRecorder.state !== 'inactive') {
      micRecorder.onstop = () => {
        micStopped = true;
        checkComplete();
      };
      micRecorder.stop();
    } else {
      micStopped = true;
    }

    if (tabRecorder && tabRecorder.state !== 'inactive') {
      tabRecorder.onstop = () => {
        tabStopped = true;
        checkComplete();
      };
      tabRecorder.stop();
    } else {
      tabStopped = true;
    }

    checkComplete();

    setTimeout(() => {
      if (!micStopped || !tabStopped) {
        reject(new Error('Recording stop timeout'));
      }
    }, 5000);
  });
}
