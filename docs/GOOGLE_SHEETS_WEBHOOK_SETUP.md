# Google Sheets Webhook Setup Guide

This guide explains how to set up the Google Apps Script webhook for real-time Google Sheets synchronization.

## Overview

The webhook system allows your Google Sheets to automatically notify the API when data is updated, ensuring instant cache synchronization without polling.

## Setup Steps

### 1. Get Your Webhook URL

Your webhook endpoint is:
```
https://zensbot.cloud/webhooks/google-sheets-update
```

**Production URL is already configured!** No need to change anything.

### 2. Get Your Webhook Secret

The webhook secret is set in your `.env` file:
```env
SHEETS_WEBHOOK_SECRET=your_secure_random_secret_here
```

### 3. Add Google Apps Script to Your Sheet

1. Open your Google Sheet
2. Go to **Extensions** > **Apps Script**
3. Delete any existing code
4. Paste the code from `scripts/google_apps_script.js` (see below)
5. Update the configuration:
   - Replace `WEBHOOK_URL` with your API URL
   - Replace `WEBHOOK_SECRET` with your secret from `.env`
6. Click **Save** (Ctrl+S or Cmd+S)
7. Click **Run** to authorize the script (first time only)

### 4. Set Up Triggers

1. In Apps Script, click the **Triggers** icon (clock) in the left sidebar
2. Click **+ Add Trigger** (bottom right)
3. Configure:
   - **Function**: `onEdit`
   - **Event source**: From spreadsheet
   - **Event type**: On edit
   - **Failure notification settings**: Immediate
4. Click **Save**

### 5. Test the Webhook

1. Edit any cell in your Google Sheet
2. Check the Apps Script execution log (View > Executions)
3. Check your API logs for webhook receipt
4. Verify data is updated in cache

## Google Apps Script Code

Save this as `scripts/google_apps_script.js` or paste directly into Apps Script:

```javascript
/**
 * Google Apps Script for Webhook Integration
 * 
 * Instructions:
 * 1. Open your Google Sheet
 * 2. Go to Extensions > Apps Script
 * 3. Paste this code
 * 4. Replace WEBHOOK_URL and WEBHOOK_SECRET with your values
 * 5. Save and authorize
 * 6. Set up triggers (see above)
 */

// ===== CONFIGURATION =====
const WEBHOOK_URL = 'https://your-api-domain.com/webhooks/google-sheets-update';
const WEBHOOK_SECRET = 'your_webhook_secret_here'; // Must match SHEETS_WEBHOOK_SECRET in .env

// ===== MAIN FUNCTIONS =====

/**
 * Triggered when any cell is edited in the spreadsheet
 */
function onEdit(e) {
  // Get sheet information
  const sheet = e.source.getActiveSheet();
  const sheetName = sheet.getName();
  const spreadsheetId = e.source.getId();
  
  // Skip if editing certain sheets (like logs, temp sheets)
  const skipSheets = ['WebhookLogs', 'Temp', 'Archive'];
  if (skipSheets.includes(sheetName)) {
    return;
  }
  
  // Call webhook
  sendWebhook(spreadsheetId, sheetName, 'updated');
}

/**
 * Triggered when a form is submitted (if you have forms)
 */
function onFormSubmit(e) {
  const sheet = e.source.getActiveSheet();
  const sheetName = sheet.getName();
  const spreadsheetId = e.source.getId();
  
  sendWebhook(spreadsheetId, sheetName, 'form_submitted');
}

/**
 * Manual trigger function - can be called from menu
 */
function manualSync() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const spreadsheetId = ss.getId();
  const sheets = ss.getSheets();
  
  // Sync all sheets
  sheets.forEach(sheet => {
    const sheetName = sheet.getName();
    sendWebhook(spreadsheetId, sheetName, 'manual_sync');
  });
  
  SpreadsheetApp.getUi().alert('All sheets synced!');
}

/**
 * Send webhook notification
 */
function sendWebhook(spreadsheetId, sheetName, action) {
  const payload = {
    spreadsheet_id: spreadsheetId,
    sheet_name: sheetName,
    action: action,
    timestamp: new Date().toISOString()
  };
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'X-Webhook-Secret': WEBHOOK_SECRET
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true // Don't throw on HTTP errors
  };
  
  try {
    const response = UrlFetchApp.fetch(WEBHOOK_URL, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    // Log the result
    logWebhookCall(sheetName, action, responseCode, responseText);
    
    if (responseCode !== 200) {
      console.error(`Webhook failed: ${responseCode} - ${responseText}`);
    }
  } catch (error) {
    console.error(`Webhook error: ${error.toString()}`);
    logWebhookCall(sheetName, action, 0, error.toString());
  }
}

/**
 * Log webhook calls for debugging
 */
function logWebhookCall(sheetName, action, responseCode, responseText) {
  try {
    // Try to log to a "WebhookLogs" sheet
    let logSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('WebhookLogs');
    
    if (!logSheet) {
      // Create log sheet if it doesn't exist
      logSheet = SpreadsheetApp.getActiveSpreadsheet().insertSheet('WebhookLogs');
      logSheet.appendRow(['Timestamp', 'Sheet', 'Action', 'Response Code', 'Response']);
    }
    
    logSheet.appendRow([
      new Date(),
      sheetName,
      action,
      responseCode,
      responseText.substring(0, 100) // Limit response length
    ]);
    
    // Keep only last 1000 rows
    if (logSheet.getLastRow() > 1000) {
      logSheet.deleteRows(2, logSheet.getLastRow() - 1000);
    }
  } catch (e) {
    // If logging fails, just continue
    console.log('Could not log webhook call');
  }
}

/**
 * Create custom menu for manual sync
 */
function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('Sync to API')
    .addItem('Sync All Sheets Now', 'manualSync')
    .addToUi();
}
```

## Environment Variables

Add these to your `.env` file:

```env
# Google Sheets API
GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/credentials.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SHEETS_SHEET_NAMES=Course_Details,Course_Links,FAQs,About_Profr,Company_Info

# Webhook Configuration
SHEETS_WEBHOOK_SECRET=your_secure_random_secret_here
SHEETS_WEBHOOK_ENABLED=true

# Fallback Polling (safety net - runs once per day)
SHEETS_FALLBACK_POLL_ENABLED=true
SHEETS_FALLBACK_POLL_INTERVAL=86400  # 24 hours in seconds

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ChromaDB Index
CHROMA_DB_PATH=./sheets_index_db
```

## Troubleshooting

### Webhook not working?

1. **Check Apps Script execution log**: View > Executions in Apps Script
2. **Check API logs**: Look for webhook receipt messages
3. **Verify webhook secret**: Must match in both Apps Script and `.env`
4. **Check URL**: Must be publicly accessible (use ngrok for local testing)
5. **Check permissions**: Apps Script needs permission to make HTTP requests

### Cache not updating?

1. **Check Redis connection**: Verify Redis is running
2. **Check API logs**: Look for sync errors
3. **Manual sync**: Use the "Sync All Sheets Now" menu in Google Sheets
4. **Check credentials**: Verify Google Sheets API credentials are valid

### Performance issues?

1. **Reduce sheet size**: Large sheets take longer to sync
2. **Check Redis memory**: Ensure Redis has enough memory
3. **Monitor API logs**: Check for slow operations

## Benefits

- ✅ **Real-time sync**: Updates happen within 1-3 seconds
- ✅ **No polling overhead**: Only syncs when data changes
- ✅ **Efficient**: Minimal API calls
- ✅ **Reliable**: Webhook + daily fallback ensures data consistency

