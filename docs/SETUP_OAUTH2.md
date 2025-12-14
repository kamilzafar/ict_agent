# OAuth2 Setup Guide for Google Sheets

This guide explains how to set up OAuth2 authentication (client ID/secret) instead of service account credentials.

## Why OAuth2?

- ✅ More secure: No JSON file with private keys
- ✅ Better control: Can revoke access easily
- ✅ Standard approach: Industry-standard authentication
- ✅ Flexible: Can use refresh tokens for long-term access

## Step 1: Create OAuth2 Credentials in Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Go to **APIs & Services** > **Credentials**
4. Click **+ CREATE CREDENTIALS** > **OAuth client ID**
5. If prompted, configure OAuth consent screen:
   - User Type: **External** (or Internal if using Google Workspace)
   - App name: `ICT Agent`
   - User support email: Your email
   - Developer contact: Your email
   - Click **Save and Continue**
   - Scopes: Click **Save and Continue** (no need to add scopes manually)
   - Test users: Add your email, click **Save and Continue**
   - Click **Back to Dashboard**
6. Create OAuth Client ID:
   - Application type: **Desktop app**
   - Name: `ICT Agent Desktop`
   - Click **Create**
7. **IMPORTANT**: Copy the **Client ID** and **Client Secret**
   - You'll need these in the next step
   - Keep them secure!

## Step 2: Get Refresh Token

You have two options:

### Option A: Using Setup Script (Recommended)

1. Set environment variables:
   ```bash
   export GOOGLE_SHEETS_CLIENT_ID="your_client_id_here"
   export GOOGLE_SHEETS_CLIENT_SECRET="your_client_secret_here"
   ```

2. Run the setup script:
   ```bash
   python scripts/setup_oauth2.py
   ```

3. A browser window will open
4. Sign in with your Google account
5. Click **Allow** to grant permissions
6. Copy the refresh token that's displayed
7. Add it to your `.env` file

### Option B: Manual OAuth Flow

1. Install required packages:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2
   ```

2. Run this Python script:
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   
   SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
   
   flow = InstalledAppFlow.from_client_config({
       "installed": {
           "client_id": "YOUR_CLIENT_ID",
           "client_secret": "YOUR_CLIENT_SECRET",
           "auth_uri": "https://accounts.google.com/o/oauth2/auth",
           "token_uri": "https://oauth2.googleapis.com/token",
           "redirect_uris": ["http://localhost"]
       }
   }, SCOPES)
   
   creds = flow.run_local_server(port=0)
   print(f"Refresh Token: {creds.refresh_token}")
   ```

3. Copy the refresh token

## Step 3: Configure Environment Variables

Add these to your `.env` file:

```env
# Google Sheets OAuth2 Configuration
GOOGLE_SHEETS_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_SHEETS_CLIENT_SECRET=your_client_secret_here
GOOGLE_SHEETS_REFRESH_TOKEN=your_refresh_token_here

# Optional: Custom token file path (default: token.pickle)
GOOGLE_SHEETS_TOKEN_PATH=token.pickle

# Spreadsheet Configuration
GOOGLE_SHEETS_SPREADSHEET_ID=1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY326_I0
GOOGLE_SHEETS_SHEET_NAMES=Course_Details,Course_Links,FAQs,About_Profr,Company_Info
```

## Step 4: Share Google Sheet

1. Open your Google Sheet
2. Click **Share** button
3. Add your Google account email (the one you used for OAuth)
4. Give it **Viewer** permission
5. Click **Send**

## Step 5: Test the Setup

1. Start your application
2. Check logs for:
   ```
   INFO: Creating credentials from refresh token
   INFO: Google Sheets API client initialized with OAuth2
   ```

3. Test webhook or make a request that uses sheets data

## Security Best Practices

### ✅ DO:
- Store credentials in `.env` file (never commit to git)
- Use environment variables in production
- Rotate refresh tokens periodically
- Use least privilege (read-only scope)
- Keep client secret secure

### ❌ DON'T:
- Commit credentials to version control
- Share client secret publicly
- Use full access scopes if read-only is enough
- Store tokens in code

## Token Refresh

The system automatically refreshes tokens when they expire. The refresh token is long-lived and doesn't expire unless:
- You revoke it in Google Cloud Console
- You change your Google account password
- 6 months of inactivity (for some account types)

If token refresh fails, you'll need to run the OAuth flow again to get a new refresh token.

## Troubleshooting

### "Invalid Grant" Error

This means your refresh token is invalid. Possible causes:
- Token was revoked
- Token expired (rare, but possible)
- Wrong client ID/secret

**Solution**: Run the OAuth flow again to get a new refresh token.

### "Access Denied" Error

This means your Google account doesn't have access to the sheet.

**Solution**: Share the Google Sheet with your account email.

### "Redirect URI Mismatch"

This happens during OAuth flow setup.

**Solution**: Make sure redirect URI in OAuth client is set to `http://localhost`

## Migration from Service Account

If you're migrating from service account to OAuth2:

1. Follow steps above to get OAuth2 credentials
2. Update `.env` file with new credentials
3. Remove `GOOGLE_SHEETS_CREDENTIALS_PATH` from `.env`
4. Restart application
5. Remove old `credentials.json` file (or keep as backup)

## Comparison: OAuth2 vs Service Account

| Feature | OAuth2 | Service Account |
|---------|--------|-----------------|
| Security | ✅ Client ID/Secret | ⚠️ JSON file with private key |
| Setup | Requires OAuth flow | Download JSON file |
| Token Management | Auto-refresh | Long-lived |
| Revocation | Easy (Google Console) | Delete JSON file |
| Best For | User-based access | Server-to-server |

For your use case (server application), OAuth2 with refresh token is more secure and flexible.
