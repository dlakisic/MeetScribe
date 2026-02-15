export let API_URL = "http://localhost:8090";
export let API_TOKEN = "";

export async function loadConfig() {
    return new Promise((resolve) => {
        chrome.storage.sync.get(['api_url', 'api_token'], (result) => {
            if (result.api_url) API_URL = result.api_url;
            if (result.api_token) API_TOKEN = result.api_token;
            resolve({ API_URL, API_TOKEN });
        });
    });
}

export function updateConfig(newUrl, newToken) {
    if (newUrl) API_URL = newUrl;
    if (newToken !== undefined) API_TOKEN = newToken; // Token can be empty string
}
