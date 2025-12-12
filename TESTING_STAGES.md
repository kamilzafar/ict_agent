# Testing Stage Implementation Locally

## Before You Commit - Complete Testing Guide

This guide will help you test the stage tracking implementation locally before pushing to production.

---

## Prerequisites

1. **Environment Setup**
   ```bash
   # Make sure you have a .env file
   cp .env.example .env
   ```

2. **Edit .env file** - Add these required variables:
   ```env
   OPENAI_API_KEY=sk-your-actual-openai-key
   API_KEY=test-api-key-12345  # Any string you want for testing
   MODEL_NAME=gpt-4o
   PINECONE_API_KEY=your-pinecone-key  # Optional but recommended
   ```

3. **Clean Start** (Optional - if you want fresh data):
   ```bash
   # Delete old memory database (ONLY for testing!)
   rm -rf memory_db/
   # OR on Windows:
   rmdir /s /q memory_db
   ```

---

## Step 1: Start the Server

```bash
# From project root directory
uv run python scripts/run_api.py
```

**Expected Output:**
```
INFO:     Initializing AI agent...
INFO:     Agent initialized successfully
INFO:     Model: gpt-4o
INFO:     Memory DB: ./memory_db
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8009 (Press CTRL+C to quit)
```

**✅ Server is ready when you see:** `Uvicorn running on...`

---

## Step 2: Test Health Endpoint (No API Key Required)

```bash
curl http://localhost:8009/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "agent_initialized": true,
  "memory_db_path": "./memory_db"
}
```

**✅ PASS if:** `agent_initialized` is `true`

---

## Step 3: Test Basic Chat (Stage Tracking)

### Test 3.1: New Conversation (Should be NEW stage)

```bash
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d '{
    "message": "Hello",
    "conversation_id": null
  }'
```

**Expected Response Structure:**
```json
{
  "response": "Assalam o Alaikum! ... [agent response]",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "turn_count": 1,
  "context_used": [],
  "stage": "NEW",
  "lead_data": {
    "name": null,
    "phone": null,
    "selected_course": null,
    "education_level": null,
    "goal": null,
    "demo_shared": false,
    "enrolled": false
  },
  "timestamp": "2025-12-12T..."
}
```

**✅ PASS if:**
- `stage` is `"NEW"`
- `lead_data` all fields are `null` or `false`
- You get a `conversation_id` back

**📝 SAVE the `conversation_id`** - You'll need it for next tests!

---

### Test 3.2: Provide Name (Should move to NAME_COLLECTED)

```bash
# Replace CONVERSATION_ID with the one from Test 3.1
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d '{
    "message": "My name is Ahmed Khan",
    "conversation_id": "CONVERSATION_ID"
  }'
```

**Expected Response:**
```json
{
  "response": "Nice to meet you Ahmed! ...",
  "conversation_id": "same-as-before",
  "turn_count": 2,
  "stage": "NAME_COLLECTED",
  "lead_data": {
    "name": "Ahmed Khan",
    "phone": null,
    "selected_course": null,
    ...
  },
  ...
}
```

**✅ PASS if:**
- `stage` changed to `"NAME_COLLECTED"`
- `lead_data.name` is **NOT** null anymore

**❌ FAIL if:**
- Stage is still `"NEW"`
- Name is still `null`

---

### Test 3.3: Mention Course (Should move to COURSE_SELECTED)

```bash
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d '{
    "message": "I want to learn about CTA course",
    "conversation_id": "CONVERSATION_ID"
  }'
```

**Expected Response:**
```json
{
  "stage": "COURSE_SELECTED",
  "lead_data": {
    "name": "Ahmed Khan",
    "selected_course": "CTA",
    ...
  },
  ...
}
```

**✅ PASS if:**
- `stage` is now `"COURSE_SELECTED"`
- `lead_data.selected_course` contains `"CTA"` or similar

**❌ FAIL if:**
- Stage didn't change
- Course is still null

---

## Step 4: Test Stage Query Endpoints

### Test 4.1: Get Stage for Conversation

```bash
curl "http://localhost:8009/conversations/CONVERSATION_ID/stage" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected Response:**
```json
{
  "conversation_id": "...",
  "stage": "COURSE_SELECTED",
  "lead_data": {
    "name": "Ahmed Khan",
    "phone": null,
    "selected_course": "CTA",
    "education_level": null,
    "goal": null,
    "demo_shared": false,
    "enrolled": false
  }
}
```

**✅ PASS if:**
- Returns correct stage
- Shows all collected data

---

### Test 4.2: Get Leads by Stage

```bash
curl "http://localhost:8009/leads/by-stage/COURSE_SELECTED" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected Response:**
```json
{
  "stage": "COURSE_SELECTED",
  "count": 1,
  "leads": [
    {
      "conversation_id": "...",
      "stage": "COURSE_SELECTED",
      "stage_updated_at": "2025-12-12T...",
      "created_at": "2025-12-12T...",
      "lead_data": {
        "name": "Ahmed Khan",
        "selected_course": "CTA",
        ...
      }
    }
  ]
}
```

**✅ PASS if:**
- `count` is at least 1
- Your test conversation appears in the list

---

### Test 4.3: Get Overall Stats

```bash
curl "http://localhost:8009/leads/stats" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected Response:**
```json
{
  "total_leads": 1,
  "by_stage": {
    "NEW": 0,
    "NAME_COLLECTED": 0,
    "COURSE_SELECTED": 1,
    "EDUCATION_COLLECTED": 0,
    "GOAL_COLLECTED": 0,
    "DEMO_SHARED": 0,
    "ENROLLED": 0,
    "LOST": 0
  },
  "conversion_rate": 0.0
}
```

**✅ PASS if:**
- `total_leads` matches number of conversations you created
- `COURSE_SELECTED` count is correct
- Numbers add up

---

### Test 4.4: Manually Update Stage

```bash
curl -X POST "http://localhost:8009/conversations/CONVERSATION_ID/update-stage?new_stage=ENROLLED" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected Response:**
```json
{
  "message": "Stage updated successfully",
  "conversation_id": "...",
  "new_stage": "ENROLLED"
}
```

**Now verify it changed:**
```bash
curl "http://localhost:8009/conversations/CONVERSATION_ID/stage" \
  -H "X-API-Key: test-api-key-12345"
```

**✅ PASS if:**
- Stage is now `"ENROLLED"`

---

## Step 5: Verify Data Persistence

### Test 5.1: Check metadata file

```bash
# View the metadata file
cat memory_db/conversations_metadata.json

# On Windows:
type memory_db\conversations_metadata.json
```

**You should see:**
```json
{
  "your-conversation-id": {
    "created_at": "...",
    "stage": "ENROLLED",
    "stage_updated_at": "...",
    "stage_history": [
      {"stage": "NEW", "timestamp": "..."},
      {"stage": "NAME_COLLECTED", "timestamp": "..."},
      {"stage": "COURSE_SELECTED", "timestamp": "..."},
      {"stage": "ENROLLED", "timestamp": "...", "manual": true}
    ],
    "lead_data": {
      "name": "Ahmed Khan",
      "phone": null,
      "selected_course": "CTA",
      ...
    },
    "turns": [...],
    "summary": null
  }
}
```

**✅ PASS if:**
- File exists
- Has your conversation
- Shows complete stage history
- Lead data is correct

---

### Test 5.2: Restart Server & Check Persistence

```bash
# Stop the server (Ctrl+C)

# Start it again
uv run python scripts/run_api.py

# Query the same conversation
curl "http://localhost:8009/conversations/CONVERSATION_ID/stage" \
  -H "X-API-Key: test-api-key-12345"
```

**✅ PASS if:**
- Data is still there after restart
- Stage is still `"ENROLLED"`
- All lead data persisted

---

## Step 6: Test API Key Protection

### Test 6.1: Request WITHOUT API Key (Should Fail)

```bash
curl "http://localhost:8009/leads/stats"
# Notice: No -H "X-API-Key: ..." header
```

**Expected Response:**
```json
{
  "detail": "API key is required. Please provide X-API-Key header."
}
```

**Status Code:** 401 Unauthorized

**✅ PASS if:**
- Request is rejected
- Error message mentions API key

---

### Test 6.2: Request with WRONG API Key (Should Fail)

```bash
curl "http://localhost:8009/leads/stats" \
  -H "X-API-Key: wrong-key-12345"
```

**Expected Response:**
```json
{
  "detail": "Invalid API key"
}
```

**Status Code:** 403 Forbidden

**✅ PASS if:**
- Request is rejected
- Error says invalid key

---

## Step 7: Test Edge Cases

### Test 7.1: Invalid Stage Name

```bash
curl -X POST "http://localhost:8009/conversations/CONVERSATION_ID/update-stage?new_stage=INVALID_STAGE" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected:**
- Status 400 Bad Request
- Error message listing valid stages

**✅ PASS if:** Request is properly rejected

---

### Test 7.2: Get Non-existent Conversation

```bash
curl "http://localhost:8009/conversations/fake-uuid-12345/stage" \
  -H "X-API-Key: test-api-key-12345"
```

**Expected Response:**
```json
{
  "conversation_id": "fake-uuid-12345",
  "stage": "NEW",
  "lead_data": {}
}
```

**✅ PASS if:** Returns default "NEW" stage for non-existent conversation

---

## Step 8: Integration Test (Full Flow)

Let's simulate a complete lead journey:

```bash
# Step 1: New lead starts chatting
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d '{"message": "Hi", "conversation_id": null}' \
  | jq -r '.conversation_id' > conv_id.txt

CONV_ID=$(cat conv_id.txt)

# Step 2: Provide name
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d "{\"message\": \"My name is Sara Ahmed\", \"conversation_id\": \"$CONV_ID\"}"

# Step 3: Select course
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key-12345" \
  -d "{\"message\": \"I want to study UK Taxation\", \"conversation_id\": \"$CONV_ID\"}"

# Step 4: Check final stage
curl "http://localhost:8009/conversations/$CONV_ID/stage" \
  -H "X-API-Key: test-api-key-12345"

# Step 5: Check stats
curl "http://localhost:8009/leads/stats" \
  -H "X-API-Key: test-api-key-12345"
```

**✅ PASS if:**
- Stage progresses through NEW → NAME_COLLECTED → COURSE_SELECTED
- Stats reflect the new lead
- All data is captured

---

## Troubleshooting

### Problem: "API key authentication is not configured"

**Solution:**
```bash
# Check .env file has API_KEY set
cat .env | grep API_KEY

# If not set, add it:
echo "API_KEY=test-api-key-12345" >> .env

# Restart server
```

---

### Problem: Stage is always "NEW"

**Possible causes:**
1. Lead data extraction not working
2. Agent not calling tools properly

**Debug:**
```bash
# Check server logs for errors
# Look for lines like: "Error extracting lead data"

# Verify memory.py has the new methods:
grep -n "def get_stage" core/memory.py
grep -n "def update_lead_field" core/memory.py
```

---

### Problem: "Agent is not initialized"

**Solution:**
```bash
# Check server logs for initialization errors
# Common causes:
# 1. OPENAI_API_KEY not set or invalid
# 2. Import errors

# Test OpenAI key:
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

---

### Problem: Server won't start - Port already in use

**Solution:**
```bash
# Find process using port 8009
# On Windows:
netstat -ano | findstr :8009
taskkill /PID <PID> /F

# On Linux/Mac:
lsof -i :8009
kill -9 <PID>

# Or use different port:
API_PORT=8010 uv run python scripts/run_api.py
```

---

## Quick Test Script

Create a file `test_stages.sh`:

```bash
#!/bin/bash

API_KEY="test-api-key-12345"
BASE_URL="http://localhost:8009"

echo "🧪 Testing Stage Implementation..."
echo ""

# Test 1: Health
echo "1️⃣  Testing health endpoint..."
curl -s "$BASE_URL/health" | jq '.agent_initialized'

# Test 2: Create conversation
echo "2️⃣  Creating new conversation..."
CONV_ID=$(curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"message": "Hello", "conversation_id": null}' \
  | jq -r '.conversation_id')

echo "   Conversation ID: $CONV_ID"

# Test 3: Check initial stage
echo "3️⃣  Checking initial stage..."
curl -s "$BASE_URL/conversations/$CONV_ID/stage" \
  -H "X-API-Key: $API_KEY" \
  | jq '.stage'

# Test 4: Provide name
echo "4️⃣  Providing name..."
curl -s -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"message\": \"My name is Test User\", \"conversation_id\": \"$CONV_ID\"}" \
  | jq '.stage'

# Test 5: Get stats
echo "5️⃣  Getting stats..."
curl -s "$BASE_URL/leads/stats" \
  -H "X-API-Key: $API_KEY" \
  | jq '.total_leads'

echo ""
echo "✅ All tests completed!"
```

**Run it:**
```bash
chmod +x test_stages.sh
./test_stages.sh
```

---

## Final Checklist Before Committing

- [ ] Server starts without errors
- [ ] Health endpoint returns `agent_initialized: true`
- [ ] Chat endpoint returns with `stage` and `lead_data` fields
- [ ] Stage changes from NEW → NAME_COLLECTED when name is provided
- [ ] Stage changes to COURSE_SELECTED when course is mentioned
- [ ] `/leads/by-stage/{stage}` returns correct leads
- [ ] `/leads/stats` returns correct counts
- [ ] `/conversations/{id}/stage` works
- [ ] Manual stage update works
- [ ] API key protection works (401 without key, 403 with wrong key)
- [ ] Data persists after server restart
- [ ] `conversations_metadata.json` contains correct structure
- [ ] Stage history is tracked
- [ ] No errors in server logs

---

## What to Check in Git Before Committing

```bash
# See what files changed
git status

# Review the changes
git diff core/memory.py
git diff core/agent.py
git diff app.py

# Make sure you don't commit:
# - .env file (contains secrets!)
# - memory_db/ folder (local data)
# - __pycache__/ folders

# Your .gitignore should have:
.env
memory_db/
__pycache__/
*.pyc
```

---

## Success Criteria

**You're ready to commit if:**

✅ All tests pass
✅ No errors in logs
✅ API responses include stage data
✅ Stages update automatically
✅ Manual stage updates work
✅ Data persists correctly
✅ API key protection works
✅ No sensitive data in git

---

**Happy Testing! 🚀**
