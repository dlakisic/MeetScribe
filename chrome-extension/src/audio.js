import { fetchAudioBlob } from './api.js';
import { getApiUrl } from './config.js';

let audio = null;
let playBtn = null;
let seekBar = null;
let volumeBar = null;
let currentTimeEl = null;
let durationEl = null;
let playerBar = null;

export function setupAudioPlayer(onTimeUpdate) {
    audio = document.getElementById('audio-player');
    playBtn = document.getElementById('audio-play-btn');
    seekBar = document.getElementById('audio-seek');
    volumeBar = document.getElementById('audio-volume');
    currentTimeEl = document.getElementById('audio-current-time');
    durationEl = document.getElementById('audio-duration');
    playerBar = document.getElementById('audio-player-bar');

    if (!audio || !playBtn) return;

    playBtn.addEventListener('click', () => {
        if (audio.paused) {
            audio.play();
            playBtn.innerHTML = '&#9646;&#9646;'; // pause icon
        } else {
            audio.pause();
            playBtn.innerHTML = '&#9654;'; // play icon
        }
    });

    audio.addEventListener('loadedmetadata', () => {
        seekBar.max = audio.duration;
        durationEl.textContent = formatAudioTime(audio.duration);
    });

    audio.addEventListener('timeupdate', () => {
        seekBar.value = audio.currentTime;
        currentTimeEl.textContent = formatAudioTime(audio.currentTime);
        if (onTimeUpdate) onTimeUpdate(audio.currentTime);
    });

    seekBar.addEventListener('input', () => {
        audio.currentTime = parseFloat(seekBar.value);
    });

    volumeBar.addEventListener('input', () => {
        audio.volume = parseFloat(volumeBar.value);
    });

    audio.addEventListener('ended', () => {
        playBtn.innerHTML = '&#9654;';
        if (onTimeUpdate) onTimeUpdate(0); // Optional: reset highlight
    });
}

function formatAudioTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
}

export function loadAudioForMeeting(meetingId, hasAudio) {
    if (!hasAudio || !playerBar || !audio) {
        if (playerBar) playerBar.style.display = 'none';
        return;
    }

    const audioUrl = `${getApiUrl()}/api/meetings/${meetingId}/audio`;
    audio.src = audioUrl;
    playBtn.innerHTML = '&#9654;';
    playerBar.style.display = 'flex';

    fetchAudioBlob(audioUrl)
        .then(blob => {
            audio.src = URL.createObjectURL(blob);
        })
        .catch(() => {
            playerBar.style.display = 'none';
        });
}

export function seekToTime(time) {
    if (audio && audio.src) {
        audio.currentTime = time;
        if (audio.paused) {
            audio.play();
            if (playBtn) playBtn.innerHTML = '&#9646;&#9646;';
        }
    }
}

export function stopAudio() {
    if (audio) {
        audio.pause();
        audio.src = '';
        if (playBtn) playBtn.innerHTML = '&#9654;';
    }
    if (playerBar) playerBar.style.display = 'none';
}
