/**
 * Google Apps Script for Webhook Integration
 * 
 * ✅ CONFIGURED FOR: https://zensbot.cloud/
 * ✅ SPREADSHEET ID: 1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10
 * 
 * Instructions:
 * 1. Open your Google Sheet: https://docs.google.com/spreadsheets/d/1lJQfvDqarAxQXWZlyfMLjEbwpkEjBBkcWvSY3226_10
 * 2. Go to Extensions > Apps Script
 * 3. Paste this entire code
 * 4. ⚠️ IMPORTANT: Replace 'your_webhook_secret_here' below with your SHEETS_WEBHOOK_SECRET from .env
 * 5. Click Save (Ctrl+S)
 * 6. To TEST: Select "testWebhook" from Run dropdown and click Run
 * 7. Set up trigger: Triggers icon → + Add Trigger → Function: onEdit, Event: On edit
 */

// ===== CONFIGURATION =====
// ✅ Webhook URL is already configured for your production API
const WEBHOOK_URL = 'https://zensbot.cloud/webhooks/google-sheets-update';

// ⚠️ ACTION REQUIRED: Replace 'your_webhook_secret_here' with the same value from your .env file
// This must match SHEETS_WEBHOOK_SECRET exactly!
const WEBHOOK_SECRET = 'l-Dcb7Rje2RlTDSjQmowWc5YycUv_e8ar7KwfPKSSec'; // ⚠️ CHANGE THIS!

// ===== MAIN FUNCTIONS =====

/**
 * Triggered when any cell is edited in the spreadsheet
 * ⚠️ DO NOT RUN THIS MANUALLY - It requires an event object from Google Sheets
 * Use testWebhook() function instead to test manually
 */
function onEdit(e) {
  // Safety check: onEdit requires an event object from Google Sheets
  if (!e || !e.source) {
    console.log('onEdit called without event object. This function should only be triggered automatically by Google Sheets when a cell is edited.');
    return;
  }
  
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
  // Safety check
  if (!e || !e.source) {
    console.log('onFormSubmit called without event object.');
    return;
  }
  
  const sheet = e.source.getActiveSheet();
  const sheetName = sheet.getName();
  const spreadsheetId = e.source.getId();
  
  sendWebhook(spreadsheetId, sheetName, 'form_submitted');
}

/**
 * Test webhook function - Safe to run manually from editor
 * Use this to test if webhook is working correctly
 */
function testWebhook() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const spreadsheetId = ss.getId();
  const testSheet = ss.getActiveSheet();
  const sheetName = testSheet.getName();
  
  console.log('Testing webhook for sheet: ' + sheetName);
  sendWebhook(spreadsheetId, sheetName, 'test');
  SpreadsheetApp.getUi().alert('Test webhook sent! Check WebhookLogs sheet for result.');
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
    } else {
      console.log(`Webhook successful: ${responseCode}`);
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
    .addItem('Test Webhook (Current Sheet)', 'testWebhook')
    .addToUi();
}
