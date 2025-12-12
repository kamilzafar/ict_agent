# Windows-Specific Issues & Fixes

## Issue: "Access is denied" when saving metadata

### Error Message:
```
PermissionError: [WinError 5] Access is denied:
'./memory_db\\conversations_metadata.json.tmp' -> './memory_db\\conversations_metadata.json'
```

### What Causes This?

1. **File is open in another program**
   - VS Code preview/editor has the file open
   - Windows File Explorer is previewing the file
   - Text editor viewing the file
   - Another instance of the app is running

2. **Antivirus software**
   - Windows Defender scanning the file
   - Third-party antivirus locking the file

3. **Windows file locking**
   - Previous crash left file handle open
   - Windows Search indexing the file

---

## ✅ **Fixed in Latest Code**

The code now includes:
- **Retry logic**: Tries 3 times with increasing delays
- **Windows-specific handling**: Uses remove + rename instead of replace
- **Graceful degradation**: Logs error but doesn't crash the app
- **Data preservation**: Data stays in memory even if save fails

---

## 🔧 **How to Fix Right Now**

### Quick Fix #1: Close All File Viewers

```bash
# Make sure these are NOT open:
# - VS Code with memory_db/conversations_metadata.json
# - Windows File Explorer viewing memory_db/
# - Any text editor with the JSON file open
```

### Quick Fix #2: Restart the Server

```bash
# Stop the server (Ctrl+C)
# Start it again
uv run python scripts/run_api.py
```

### Quick Fix #3: Delete the Lock File

```bash
# Stop the server first!
# Then delete the temp file:
del memory_db\conversations_metadata.json.tmp

# Start server again
uv run python scripts/run_api.py
```

### Quick Fix #4: Check for Multiple Instances

```bash
# Check if multiple servers are running
netstat -ano | findstr :8009

# If you see multiple entries, kill them:
taskkill /F /PID <PID>

# Then start fresh
uv run python scripts/run_api.py
```

---

## 🛡️ **Prevention Tips**

### 1. Don't Open metadata JSON in VS Code

VS Code keeps files open in the background. If you need to view it:

```bash
# Use command line instead:
type memory_db\conversations_metadata.json | more

# Or copy it first:
copy memory_db\conversations_metadata.json temp_view.json
# Then view temp_view.json in VS Code
```

### 2. Exclude from Antivirus

Add `memory_db/` folder to Windows Defender exclusions:

```
1. Open Windows Security
2. Go to "Virus & threat protection"
3. Click "Manage settings"
4. Scroll to "Exclusions"
5. Click "Add or remove exclusions"
6. Add folder: C:\Users\User\Documents\GitHub\ict_agent\memory_db
```

### 3. Use a Different Directory (Optional)

If issues persist, store metadata outside project folder:

```env
# In .env file:
MEMORY_DB_PATH=C:\Users\User\AppData\Local\ict_agent\memory_db
```

---

## 🔍 **Verify the Fix Works**

After updating the code, test it:

```bash
# 1. Stop server (Ctrl+C)

# 2. Delete old metadata to start fresh:
del memory_db\conversations_metadata.json
del memory_db\conversations_metadata.json.tmp

# 3. Start server
uv run python scripts/run_api.py

# 4. Send a test message
curl -X POST "http://localhost:8009/chat" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: test-api-key-12345" ^
  -d "{\"message\": \"Hello\", \"conversation_id\": null}"

# 5. Check if metadata file was created
dir memory_db\conversations_metadata.json
```

**✅ SUCCESS if:** File exists and no errors in logs

---

## 🐛 **Still Getting Errors?**

### Check Server Logs

Look for these messages:
```
✅ GOOD: No errors
❌ BAD: "Failed to save metadata"
❌ BAD: "Metadata save failed, but data is preserved in memory"
```

### Enable Debug Logging

Edit `.env`:
```env
LOG_LEVEL=debug
```

Restart server and check logs for more details.

### Manual Test - Write Permission

```bash
# Test if you can write to the directory:
echo test > memory_db\test.txt

# If this fails, you have a permissions issue:
# Right-click memory_db folder → Properties → Security
# Make sure your user has "Full Control"
```

---

## 📝 **What Changed in the Fix**

### Before (Old Code):
```python
# Simple replace - fails on Windows if file is locked
os.replace(temp_file, self.metadata_file)
```

### After (New Code):
```python
# Windows-specific with retry logic
if sys.platform == "win32":
    # Try 3 times
    for attempt in range(3):
        try:
            os.remove(self.metadata_file)  # Remove first
            os.rename(temp_file, self.metadata_file)  # Then rename
            break
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))  # Wait and retry
```

**Key improvements:**
- ✅ Detects Windows platform
- ✅ Uses remove + rename (more reliable on Windows)
- ✅ Retries 3 times with increasing delays
- ✅ Doesn't crash if save fails (logs warning instead)
- ✅ Data preserved in memory for next save attempt

---

## 🎯 **Best Practices**

1. **Don't view metadata files while server is running**
   - Use API endpoints instead: `/conversations/{id}`

2. **Use proper shutdown**
   - Always Ctrl+C to stop server gracefully
   - Don't kill process forcefully

3. **Regular backups**
   ```bash
   # Backup metadata before testing:
   copy memory_db\conversations_metadata.json memory_db\backup.json
   ```

4. **Monitor disk space**
   - Metadata file grows over time
   - Consider cleanup of old conversations

---

## ⚡ **Performance Note**

The new retry logic adds minimal overhead:
- **1st attempt**: Instant (no delay)
- **2nd attempt**: 100ms delay (only if 1st fails)
- **3rd attempt**: 200ms delay (only if 2nd fails)

Total max delay: 300ms (only in worst case)

Normal operation: **0ms overhead** (succeeds on first try)

---

## 🆘 **Emergency Recovery**

If metadata is corrupted or locked:

```bash
# 1. Stop server

# 2. Backup current data
copy memory_db\conversations_metadata.json memory_db\backup_$(date).json

# 3. Delete problematic files
del memory_db\conversations_metadata.json
del memory_db\conversations_metadata.json.tmp

# 4. Start server (creates fresh metadata)
uv run python scripts/run_api.py

# 5. If you need old data, manually merge from backup
```

---

## ✅ **Verification Checklist**

After applying the fix:

- [ ] Server starts without errors
- [ ] Can send chat messages successfully
- [ ] No "Access denied" errors in logs
- [ ] `conversations_metadata.json` file is created
- [ ] File is updated after each message
- [ ] No `.tmp` files left behind
- [ ] Server shutdown is clean (Ctrl+C works)

---

**You're all set! The fix handles Windows file locking properly now.** 🚀
