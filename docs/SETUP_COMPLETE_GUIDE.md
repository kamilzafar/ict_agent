# Complete Setup Guide - Google Sheets Caching System

## Your Configuration

- **API Base URL**: `https://zensbot.cloud/`
- **Webhook Endpoint**: `https://zensbot.cloud/webhooks/google-sheets-update`
- **Google Sheet ID**: `1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10`
- **Sheets to Cache**: `Course_Details`, `Course_Links`, `FAQs`, `About_Profr`, `Company_Info`

## Step-by-Step Setup

### Step 1: Environment Variables

Add these to your `.env` file:

```env
# Google Sheets API Configuration
GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/your/credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10
GOOGLE_SHEETS_SHEET_NAMES=Course_Details,Course_Links,FAQs,About_Profr,Company_Info

# Webhook Configuration
SHEETS_WEBHOOK_SECRET=generate_a_secure_random_string_here
SHEETS_WEBHOOK_ENABLED=true

# Fallback Polling (safety net - runs once per day)
SHEETS_FALLBACK_POLL_ENABLED=true
SHEETS_FALLBACK_POLL_INTERVAL=86400  # 24 hours

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ChromaDB Index
CHROMA_DB_PATH=./sheets_index_db
```

**Important**: 
- Generate a secure random string for `SHEETS_WEBHOOK_SECRET` (e.g., use `openssl rand -hex 32`)
- Make sure `GOOGLE_SHEETS_CREDENTIALS_PATH` points to your service account JSON file

### Step 2: Google Service Account Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable **Google Sheets API**
4. Create a **Service Account**:
   - Go to **IAM & Admin** > **Service Accounts**
   - Click **Create Service Account**
   - Give it a name (e.g., "sheets-cache-service")
   - Click **Create and Continue**
   - Skip role assignment, click **Done**
5. Create and download credentials:
   - Click on the service account
   - Go to **Keys** tab
   - Click **Add Key** > **Create new key**
   - Choose **JSON** format
   - Download the JSON file
   - Save it to your project directory (e.g., `credentials/google-sheets-service-account.json`)
6. Share your Google Sheet with the service account:
   - Open the downloaded JSON file
   - Copy the `client_email` value (e.g., `sheets-cache-service@your-project.iam.gserviceaccount.com`)
   - Open your Google Sheet: https://docs.google.com/spreadsheets/d/1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10
   - Click **Share** button
   - Paste the service account email
   - Give it **Viewer** access
   - Click **Send**

### Step 3: Install Google Apps Script

1. Open your Google Sheet: https://docs.google.com/spreadsheets/d/1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10
2. Go to **Extensions** > **Apps Script**
3. Delete any existing code
4. Copy the entire content from `scripts/google_apps_script.js`
5. **IMPORTANT**: Update line 15:
   ```javascript
   const WEBHOOK_SECRET = 'your_webhook_secret_here'; // Replace with your SHEETS_WEBHOOK_SECRET from .env
   ```
   Replace `'your_webhook_secret_here'` with the same value you set in `.env` for `SHEETS_WEBHOOK_SECRET`
6. Click **Save** (Ctrl+S or Cmd+S)
7. Click **Run** (play button) to authorize:
   - First time: Click **Review Permissions**
   - Select your Google account
   - Click **Advanced** > **Go to [Project Name] (unsafe)**
   - Click **Allow**

### Step 4: Set Up Webhook Trigger

1. In Apps Script, click the **Triggers** icon (clock) in the left sidebar
2. Click **+ Add Trigger** (bottom right)
3. Configure:
   - **Function**: `onEdit`
   - **Event source**: From spreadsheet
   - **Event type**: On edit
   - **Failure notification settings**: Immediate
4. Click **Save**

### Step 5: Test the Setup

1. **Test Webhook Manually**:
   - In Google Sheets, go to **Sync to API** menu (top bar)
   - Click **Sync All Sheets Now**
   - Check the **WebhookLogs** sheet (created automatically) for results
   - Should see status code 200

2. **Test by Editing**:
   - Edit any cell in `Course_Details` sheet
   - Check **WebhookLogs** sheet - should see a new entry
   - Check your API logs - should see webhook receipt

3. **Verify Cache**:
   - Restart your API server
   - Check logs for "Pre-loading Google Sheets data..."
   - Should see "Google Sheets cache initialized successfully"

### Step 6: Verify Everything Works

1. **Check API Health**:
   ```bash
   curl https://zensbot.cloud/health
   ```

2. **Test Webhook Endpoint** (replace `your_secret` with actual secret):
   ```bash
   curl -X POST https://zensbot.cloud/webhooks/google-sheets-update \
     -H "Content-Type: application/json" \
     -H "X-Webhook-Secret: your_secret" \
     -d '{
       "spreadsheet_id": "1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10",
       "sheet_name": "Course_Details",
       "action": "updated"
     }'
   ```

3. **Send a Test Chat Message**:
   - The agent should now use cached Google Sheets data
   - No tool calls needed for course information
   - Response should be faster

## Troubleshooting

### Webhook Not Working?

1. **Check WebhookLogs sheet** in Google Sheets
2. **Verify secret matches**: Must be identical in both `.env` and Apps Script
3. **Check API logs** for webhook receipt
4. **Test manually**: Use "Sync All Sheets Now" menu option

### Cache Not Updating?

1. **Check Redis is running**: `redis-cli ping` should return `PONG`
2. **Check API logs** for sync errors
3. **Manual sync**: Use "Sync All Sheets Now" in Google Sheets
4. **Verify credentials**: Service account JSON file path is correct

### Service Account Issues?

1. **Verify sheet is shared**: Service account email must have access
2. **Check API is enabled**: Google Sheets API must be enabled
3. **Verify credentials path**: File exists and path is correct in `.env`

## What Happens Now?

### On Startup:
- ✅ All 5 sheets are pre-loaded into cache
- ✅ ChromaDB semantic index is created
- ✅ Data stored in Redis
- ✅ Background polling task starts (daily fallback)

### When You Edit Google Sheet:
- ✅ Webhook triggers within 1-3 seconds
- ✅ Cache updates automatically
- ✅ ChromaDB re-indexes
- ✅ Next user request uses fresh data

### When User Sends Message:
- ✅ Agent checks conversation stage
- ✅ Relevant sheet data injected automatically (no tool calls!)
- ✅ Fast response using cached data
- ✅ No Google Sheets API calls during user requests

## Success Indicators

You'll know it's working when:
- ✅ API logs show "Google Sheets cache initialized successfully"
- ✅ WebhookLogs sheet shows 200 status codes
- ✅ Chat responses include course data without tool calls
- ✅ Response times are faster
- ✅ No errors in API logs

## Support

If you encounter issues:
1. Check `WebhookLogs` sheet in Google Sheets
2. Review API logs for errors
3. Verify all environment variables are set
4. Test webhook manually using curl command above

---

**Your system is now configured for maximum efficiency!** 🚀
