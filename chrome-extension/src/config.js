const config = {
    apiUrl: "http://localhost:8090",
    apiToken: "",
};

export function getApiUrl() { return config.apiUrl; }
export function getApiToken() { return config.apiToken; }

export async function loadConfig() {
    return new Promise((resolve) => {
        chrome.storage.sync.get(['api_url', 'api_token'], (result) => {
            if (result.api_url) config.apiUrl = result.api_url;
            if (result.api_token) config.apiToken = result.api_token;
            resolve({ apiUrl: config.apiUrl, apiToken: config.apiToken });
        });
    });
}

export function updateConfig(newUrl, newToken) {
    if (newUrl) config.apiUrl = newUrl;
    if (newToken !== undefined) config.apiToken = newToken;
}
