/**
 * MeetScribe Unified Config Manager
 *
 * Single source of truth for all extension configuration.
 * Uses chrome.storage.local with unified snake_case keys.
 * Includes one-shot migration from old fragmented keys.
 */

const DEFAULTS = {
    api_url: 'http://localhost:8090',
    api_token: '',
    auto_start_delay: 5,
    speaker_name: 'Moi',
    max_screenshots: 20,
};

// In-memory cache (populated by loadConfig)
let _config = { ...DEFAULTS };

/**
 * Load config from storage, migrating old keys if needed.
 * Call this once at startup in every context (dashboard, service-worker, popup).
 */
export async function loadConfig() {
    // Try loading unified config first
    const stored = await chrome.storage.local.get(Object.keys(DEFAULTS));

    // Check if we need to migrate from old fragmented keys
    if (!stored.api_url) {
        await _migrateOldConfig();
        const migrated = await chrome.storage.local.get(Object.keys(DEFAULTS));
        _config = { ...DEFAULTS, ...migrated };
    } else {
        _config = { ...DEFAULTS, ...stored };
    }

    return { ..._config };
}

/**
 * One-shot migration: read old keys from sync + local, write unified format.
 */
async function _migrateOldConfig() {
    const oldSync = await chrome.storage.sync.get(['api_url', 'api_token']);
    const oldLocal = await chrome.storage.local.get([
        'backendUrl', 'apiToken', 'autoStartDelay', 'speakerName',
    ]);

    const migrated = {};

    // Prefer sync api_url (from dashboard), fallback to local backendUrl (from options)
    if (oldSync.api_url) migrated.api_url = oldSync.api_url;
    else if (oldLocal.backendUrl) migrated.api_url = oldLocal.backendUrl;

    if (oldSync.api_token) migrated.api_token = oldSync.api_token;
    else if (oldLocal.apiToken) migrated.api_token = oldLocal.apiToken;

    if (oldLocal.autoStartDelay) migrated.auto_start_delay = oldLocal.autoStartDelay;
    if (oldLocal.speakerName) migrated.speaker_name = oldLocal.speakerName;

    if (Object.keys(migrated).length > 0) {
        await chrome.storage.local.set(migrated);
        // Cleanup old keys
        await chrome.storage.sync.remove(['api_url', 'api_token']).catch(() => {});
        await chrome.storage.local.remove(['backendUrl', 'apiToken', 'autoStartDelay', 'speakerName']).catch(() => {});
        console.log('[MeetScribe] Config migrated to unified format', migrated);
    }
}

/**
 * Save config updates (partial merge).
 */
export async function saveConfig(updates) {
    Object.assign(_config, updates);
    await chrome.storage.local.set(updates);
}

/**
 * Get the full config (from memory cache).
 */
export function getConfig() {
    return { ..._config };
}

// Convenience getters (backward-compatible with api.js imports)
export function getApiUrl() { return _config.api_url; }
export function getApiToken() { return _config.api_token; }
export function getAutoStartDelay() { return _config.auto_start_delay; }
export function getSpeakerName() { return _config.speaker_name; }
export function getMaxScreenshots() { return _config.max_screenshots; }

/**
 * Update in-memory config (no persistence). Kept for backward compat.
 * @deprecated Use saveConfig() instead.
 */
export function updateConfig(newUrl, newToken) {
    if (newUrl) _config.api_url = newUrl;
    if (newToken !== undefined) _config.api_token = newToken;
}
