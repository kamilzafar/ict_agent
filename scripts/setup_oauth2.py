"""Script to set up OAuth2 credentials for Google Sheets API.

This script helps you obtain the refresh token needed for server-to-server
authentication with Google Sheets API.

Run this once to get your refresh token, then use it in your .env file.
"""
import os
import json
import pickle
from pathlib import Path
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
    
    # Try to load from credential.json file first
    client_id = None
    client_secret = None
    cred_file = Path("credential.json")
    
    if cred_file.exists():
        try:
            with open(cred_file, 'r') as f:
                cred_data = json.load(f)
            
            # Check for "web" or "installed" key
            if "web" in cred_data:
                web_config = cred_data["web"]
                client_id = web_config.get("client_id")
                client_secret = web_config.get("client_secret")
                print(f"✓ Found OAuth2 credentials in credential.json")
            elif "installed" in cred_data:
                installed_config = cred_data["installed"]
                client_id = installed_config.get("client_id")
                client_secret = installed_config.get("client_secret")
                print(f"✓ Found OAuth2 credentials in credential.json")
        except Exception as e:
            print(f"⚠ Could not read credential.json: {e}")
    
    # Fall back to environment variables
    if not client_id:
        client_id = os.getenv("GOOGLE_SHEETS_CLIENT_ID")
    if not client_secret:
        client_secret = os.getenv("GOOGLE_SHEETS_CLIENT_SECRET")
    
    # Prompt if still not found
    if not client_id:
        client_id = input("Enter your Google OAuth2 Client ID: ").strip()
    if not client_secret:
        client_secret = input("Enter your Google OAuth2 Client Secret: ").strip()
    
    # Determine client type from credential.json or default to "installed"
    client_type = "installed"
    redirect_uris = ["http://localhost"]
    oauth_port = 8009  # Default port for OAuth callback
    
    if cred_file.exists():
        try:
            with open(cred_file, 'r') as f:
                cred_data = json.load(f)
            if "web" in cred_data:
                client_type = "web"
                # For web clients, use port 8009 (matching API server)
                redirect_uris = [
                    "http://localhost:8009",
                    "http://localhost:8009/callback",
                    "http://localhost:8009/oauth2callback",
                    "http://localhost",
                    "http://127.0.0.1:8009",
                    "http://127.0.0.1:8009/callback"
                ]
                oauth_port = 8009
                print("✓ Detected 'web' type OAuth client")
        except:
            pass
    
    # Create OAuth2 flow configuration
    client_config = {
        client_type: {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": redirect_uris
        }
    }
    
    print("\nStarting OAuth2 flow...")
    print("A browser window will open. Please authorize the application.")
    print()
    print("⚠ IMPORTANT: Make sure these redirect URIs are added in Google Cloud Console:")
    for uri in redirect_uris[:3]:  # Show first 3
        print(f"   - {uri}")
    print()
    
    # Use port 8009 for web clients to match your API server
    # Note: This is just for OAuth callback, your API server can run on the same port
    if client_type == "web":
        port = oauth_port
        print(f"Using port {port} for OAuth callback (matching your API server port)...")
        print("⚠ Make sure port 8009 is available or temporarily stop your API server")
    else:
        port = 0  # Random port for installed apps
    
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=port, open_browser=True)
    
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
        print("2. For 'Web application' type, add these authorized redirect URIs:")
        print("   - http://localhost:8009")
        print("   - http://localhost:8009/callback")
        print("   - http://localhost:8009/oauth2callback")
        print("   - http://localhost")
        print("3. For 'Desktop app' type, add: http://localhost")
        print("\nTo fix redirect_uri_mismatch:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials")
        print("2. Click on your OAuth 2.0 Client ID")
        print("3. Add the redirect URIs listed above")
        print("4. Click 'Save'")
        print("5. Stop your API server (if running on port 8009)")
        print("6. Run this script again")
        print("\nNote: The OAuth callback uses port 8009 temporarily.")
        print("      After getting the refresh token, you can restart your API server.")
