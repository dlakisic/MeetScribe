/**
 * Settings modal management.
 */

import * as Config from './config.js';

export function setupSettingsHandlers(loadMeetings) {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsModal = document.getElementById('settings-modal');
    const closeSettings = document.getElementById('close-settings');
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    const apiUrlInput = document.getElementById('api-url-input');
    const apiTokenInput = document.getElementById('api-token-input');

    if (!settingsBtn || !settingsModal) return;

    settingsBtn.addEventListener('click', () => {
        settingsModal.style.display = 'flex';
        apiUrlInput.value = Config.getApiUrl();
        apiTokenInput.value = Config.getApiToken();
    });

    closeSettings.addEventListener('click', () => {
        settingsModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target == settingsModal) settingsModal.style.display = 'none';
    });

    saveSettingsBtn.addEventListener('click', async () => {
        const newUrl = apiUrlInput.value.trim().replace(/\/$/, "");
        const newToken = apiTokenInput.value.trim();
        if (newUrl) {
            await Config.saveConfig({ api_url: newUrl, api_token: newToken });
            settingsModal.style.display = 'none';
            loadMeetings();
        }
    });
}
