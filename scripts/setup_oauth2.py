"""Script to set up OAuth2 credentials for Google Sheets API.

This script helps you obtain the refresh token needed for server-to-server
authentication with Google Sheets API.

Run this once to get your refresh token, then use it in your .env file.
"""
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# OAuth2 scopes
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Token file
TOKEN_FILE = 'token.pickle'

def setup_oauth2():
    """Run OAuth2 flow to get refresh token."""
    print("=" * 60)
    print("Google Sheets OAuth2 Setup")
    print("=" * 60)
    print()
    
    # Get client ID and secret from environment or input
    client_id = os.getenv("GOOGLE_SHEETS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_SHEETS_CLIENT_SECRET")
    
    if not client_id:
        client_id = input("Enter your Google OAuth2 Client ID: ").strip()
    if not client_secret:
        client_secret = input("Enter your Google OAuth2 Client Secret: ").strip()
    
    # Create OAuth2 flow
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    print("\nStarting OAuth2 flow...")
    print("A browser window will open. Please authorize the application.")
    print()
    
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    
    # Save credentials
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)
    
    print("\n" + "=" * 60)
    print("OAuth2 Setup Complete!")
    print("=" * 60)
    print()
    print("Your refresh token:")
    print("-" * 60)
    print(creds.refresh_token)
    print("-" * 60)
    print()
    print("Add this to your .env file:")
    print(f"GOOGLE_SHEETS_REFRESH_TOKEN={creds.refresh_token}")
    print()
    print(f"Token saved to: {TOKEN_FILE}")
    print("You can delete this file after adding refresh_token to .env")
    print()

if __name__ == "__main__":
    try:
        setup_oauth2()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
    except Exception as e:
        print(f"\n\nError: {e}")
        print("\nMake sure you have:")
        print("1. Created OAuth2 credentials in Google Cloud Console")
        print("2. Set application type to 'Desktop app'")
        print("3. Added authorized redirect URI: http://localhost")
