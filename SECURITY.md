## Security

Do not commit secrets. Use chrome.storage.local for the user’s OpenAI API key and never hardcode keys.
Grant the minimum extension permissions required. Use host_permissions only for domains we truly need.
All network calls must validate expected URLs and handle failures safely.
