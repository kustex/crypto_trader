import os

# Define the file path for storing API credentials
API_CREDENTIALS_FILE = os.path.expanduser("~/.crypto_trading_api_credentials")

def load_api_credentials():
    """Load API credentials from a local hidden file."""
    api_key, api_secret, api_passphrase = "", "", ""

    try:
        with open(API_CREDENTIALS_FILE, "r") as f:
            lines = f.read().splitlines()
            api_key = lines[0] if len(lines) > 0 else ""
            api_secret = lines[1] if len(lines) > 1 else ""
            api_passphrase = lines[2] if len(lines) > 2 else ""
    except FileNotFoundError:
        pass  # File doesn't exist yet, return empty credentials

    return api_key, api_secret, api_passphrase

def save_api_credentials(api_key, api_secret, api_passphrase):
    """Save API credentials to a hidden file."""
    with open(API_CREDENTIALS_FILE, "w") as f:
        f.write(f"{api_key}\n{api_secret}\n{api_passphrase}\n")

    # Secure the file (Linux/macOS only)
    if os.name != "nt":
        os.chmod(API_CREDENTIALS_FILE, 0o600)  # Restrict file access

    print("✅ API Credentials Saved Successfully!")
