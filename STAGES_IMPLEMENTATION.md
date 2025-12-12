# Stage Tracking Implementation Guide

## What is Stage Tracking?

Stage tracking helps you know where each lead is in the enrollment process. Instead of guessing, you can see exactly which step they're on - did they just start chatting? Did they select a course? Did they get the demo video?

Think of it like a pipeline: **NEW → NAME → COURSE → EDUCATION → GOAL → DEMO → ENROLLED**

---

## The 8 Stages

Every lead goes through these stages:

1. **NEW** - Just started talking, haven't collected anything yet
2. **NAME_COLLECTED** - We got their name
3. **COURSE_SELECTED** - They picked a course they're interested in
4. **EDUCATION_COLLECTED** - We know their education level
5. **GOAL_COLLECTED** - We know their goals/motivation
6. **DEMO_SHARED** - Demo video has been sent to them
7. **ENROLLED** - They successfully enrolled (manually set)
8. **LOST** - Lead went cold or not interested (manually set)

---

## How It Works (Simple Explanation)

### Automatic Stage Detection

The system automatically moves leads through stages based on what information is collected:

```
User: "My name is Ahmed"
→ Stage changes to NAME_COLLECTED

User: "I want to learn CTA"
→ Stage changes to COURSE_SELECTED

Agent calls append_lead_to_rag_sheets tool (before demo)
→ Stage changes to DEMO_SHARED
```

### Where Data is Stored

Everything is stored in `conversations_metadata.json` file:

```json
{
  "conversation-id-here": {
    "stage": "COURSE_SELECTED",
    "stage_updated_at": "2025-12-12T15:30:00",
    "stage_history": [
      {"stage": "NEW", "timestamp": "2025-12-12T15:00:00"},
      {"stage": "NAME_COLLECTED", "timestamp": "2025-12-12T15:10:00"},
      {"stage": "COURSE_SELECTED", "timestamp": "2025-12-12T15:30:00"}
    ],
    "lead_data": {
      "name": "Ahmed",
      "phone": "+92 300 1234567",
      "selected_course": "CTA",
      "education_level": "Graduate",
      "goal": "Career switch",
      "demo_shared": false,
      "enrolled": false
    },
    "turns": [...],
    "summary": "..."
  }
}
```

---

## Files Modified

### 1. `core/memory.py` - The Storage System

**What was added:**
- Stage definitions (NEW, NAME_COLLECTED, etc.)
- Methods to update lead data
- Methods to automatically detect and change stages
- Methods to get leads by stage
- Methods to get statistics

**Key methods:**
```python
memory.update_lead_field(conversation_id, "name", "Ahmed")  # Updates name and stage
memory.get_stage(conversation_id)  # Returns current stage
memory.get_lead_data(conversation_id)  # Returns all collected data
memory.get_leads_by_stage("COURSE_SELECTED")  # Get all leads in that stage
memory.get_all_stage_stats()  # Get counts for all stages
```

### 2. `core/agent.py` - The Brain

**What was added:**
- `_extract_and_update_lead_data()` method that:
  - Watches for the `append_lead_to_rag_sheets` tool being called
  - Extracts name, phone, course, education, goal from tool arguments
  - Detects course mentions in conversation (CTA, ACCA, etc.)
  - Automatically updates stages

**When it runs:**
- After every conversation turn
- Checks what the AI said and did
- Updates lead data and stages accordingly

**Chat method now returns:**
```python
{
  "response": "...",
  "conversation_id": "...",
  "turn_count": 5,
  "context_used": [...],
  "stage": "COURSE_SELECTED",  # ← NEW!
  "lead_data": {                # ← NEW!
    "name": "Ahmed",
    "phone": "+92 300 1234567",
    "selected_course": "CTA",
    "education_level": "Graduate",
    "goal": "Career switch",
    "demo_shared": false,
    "enrolled": false
  }
}
```

### 3. `app.py` - The API

**What was changed:**
- `ChatResponse` model now includes `stage` and `lead_data`

**What was added - 4 New API Endpoints:**

1. **GET /leads/by-stage/{stage}** - Get all leads in a specific stage
2. **GET /leads/stats** - Get overall statistics
3. **GET /conversations/{conversation_id}/stage** - Get stage for one conversation
4. **POST /conversations/{conversation_id}/update-stage** - Manually change stage

---

## API Usage Examples

### 1. Send a Chat Message (Now includes stage info)

```bash
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message": "My name is Ahmed and I want to learn CTA",
    "conversation_id": null
  }'
```

**Response:**
```json
{
  "response": "Great to meet you Ahmed! CTA is an excellent choice...",
  "conversation_id": "uuid-here",
  "turn_count": 1,
  "stage": "COURSE_SELECTED",
  "lead_data": {
    "name": "Ahmed",
    "phone": null,
    "selected_course": "CTA",
    "education_level": null,
    "goal": null,
    "demo_shared": false,
    "enrolled": false
  },
  "timestamp": "2025-12-12T15:30:00"
}
```

### 2. Get All Leads Who Selected a Course

```bash
curl "http://localhost:8009/leads/by-stage/COURSE_SELECTED" \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "stage": "COURSE_SELECTED",
  "count": 15,
  "leads": [
    {
      "conversation_id": "uuid-1",
      "stage": "COURSE_SELECTED",
      "stage_updated_at": "2025-12-12T15:30:00",
      "created_at": "2025-12-12T15:00:00",
      "lead_data": {
        "name": "Ahmed",
        "selected_course": "CTA",
        ...
      }
    },
    ...
  ]
}
```

### 3. Get Overall Lead Statistics

```bash
curl "http://localhost:8009/leads/stats" \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "total_leads": 150,
  "by_stage": {
    "NEW": 20,
    "NAME_COLLECTED": 15,
    "COURSE_SELECTED": 25,
    "EDUCATION_COLLECTED": 18,
    "GOAL_COLLECTED": 22,
    "DEMO_SHARED": 30,
    "ENROLLED": 18,
    "LOST": 2
  },
  "conversion_rate": 12.0
}
```

### 4. Get Stage for One Conversation

```bash
curl "http://localhost:8009/conversations/uuid-here/stage" \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "conversation_id": "uuid-here",
  "stage": "GOAL_COLLECTED",
  "lead_data": {
    "name": "Ahmed",
    "phone": "+92 300 1234567",
    "selected_course": "CTA",
    "education_level": "Graduate",
    "goal": "Career switch to taxation",
    "demo_shared": false,
    "enrolled": false
  }
}
```

### 5. Manually Update a Stage

```bash
curl -X POST "http://localhost:8009/conversations/uuid-here/update-stage?new_stage=ENROLLED" \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "message": "Stage updated successfully",
  "conversation_id": "uuid-here",
  "new_stage": "ENROLLED"
}
```

---

## Common Use Cases

### Use Case 1: Find All Leads Who Got Demo But Haven't Enrolled

```bash
curl "http://localhost:8009/leads/by-stage/DEMO_SHARED" \
  -H "X-API-Key: your-api-key"
```

These are your warm leads who need follow-up!

### Use Case 2: Track Today's Performance

```bash
curl "http://localhost:8009/leads/stats" -H "X-API-Key: your-api-key"
```

See how many leads you got, how many are in each stage, and your conversion rate.

### Use Case 3: Mark Someone as Enrolled After Payment

```bash
curl -X POST "http://localhost:8009/conversations/uuid/update-stage?new_stage=ENROLLED" \
  -H "X-API-Key: your-api-key"
```

### Use Case 4: Find Cold Leads

```bash
curl "http://localhost:8009/leads/by-stage/LOST" \
  -H "X-API-Key: your-api-key"
```

---

## How Automatic Stage Detection Works

### Detection Logic

The system checks in order:

1. **Is `enrolled` = true?** → Stage = ENROLLED
2. **Is `demo_shared` = true?** → Stage = DEMO_SHARED
3. **Is `goal` filled?** → Stage = GOAL_COLLECTED
4. **Is `education_level` filled?** → Stage = EDUCATION_COLLECTED
5. **Is `selected_course` filled?** → Stage = COURSE_SELECTED
6. **Is `name` filled?** → Stage = NAME_COLLECTED
7. **Nothing filled?** → Stage = NEW

### When Detection Happens

After every chat turn:
1. User sends message
2. Agent responds
3. Agent checks all messages for tool calls
4. Agent extracts data from tool calls
5. Agent updates lead_data
6. Stage automatically updates based on what's filled

### Example Flow

```
Turn 1:
User: "Hello"
→ Stage: NEW (nothing collected yet)

Turn 2:
User: "My name is Ahmed"
→ name gets updated
→ Stage: NAME_COLLECTED

Turn 3:
User: "I want to study CTA course"
→ selected_course = "CTA"
→ Stage: COURSE_SELECTED

Turn 4:
Agent calls append_lead_to_rag_sheets with Ahmed's info
→ demo_shared = true
→ Stage: DEMO_SHARED
```

---

## Stage History Tracking

Every time a stage changes, it's recorded:

```json
"stage_history": [
  {
    "stage": "NEW",
    "timestamp": "2025-12-12T15:00:00"
  },
  {
    "stage": "NAME_COLLECTED",
    "timestamp": "2025-12-12T15:05:00"
  },
  {
    "stage": "COURSE_SELECTED",
    "timestamp": "2025-12-12T15:10:00"
  },
  {
    "stage": "DEMO_SHARED",
    "timestamp": "2025-12-12T15:15:00"
  }
]
```

This lets you:
- See how long it took to move between stages
- Identify bottlenecks in your funnel
- Track conversion speed

---

## Thread Safety

All stage operations are **thread-safe**:
- Multiple requests can happen at the same time
- No race conditions
- No data corruption
- Uses Python locks internally

---

## Integration with Existing Code

The stage tracking works seamlessly with your existing code:

✅ **No breaking changes** - Old conversations still work
✅ **Automatic migration** - Old conversations get initialized with stages when accessed
✅ **Backward compatible** - If stage data is missing, defaults to "NEW"
✅ **Works with API key auth** - All new endpoints require authentication

---

## What Happens to Old Conversations?

When an old conversation (created before stage tracking) is accessed:

1. System detects it has no `lead_data` field
2. Automatically initializes it with default structure:
   ```json
   {
     "stage": "NEW",
     "lead_data": {
       "name": null,
       "phone": null,
       ...
     }
   }
   ```
3. From that point on, it tracks stages normally

**No data is lost!**

---

## Performance Impact

**Minimal** - Stage tracking is lightweight:
- Updates happen in-memory with locks (fast)
- Only writes to disk when metadata is saved (already happening)
- No extra API calls to OpenAI
- No extra database queries
- No noticeable slowdown

---

## Testing the Implementation

### Step 1: Start the server
```bash
uv run python scripts/run_api.py
```

### Step 2: Send a test message
```bash
curl -X POST "http://localhost:8009/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "message": "Hi, my name is Test User",
    "conversation_id": null
  }'
```

Check the response - you should see `"stage": "NAME_COLLECTED"`

### Step 3: Check stats
```bash
curl "http://localhost:8009/leads/stats" \
  -H "X-API-Key": "your-api-key"
```

You should see at least 1 lead in NAME_COLLECTED stage.

---

## Future Enhancements (Not Implemented Yet)

Ideas for future improvements:

1. **Time-based stage changes** - Auto-mark as LOST if no response in 7 days
2. **Stage webhooks** - Notify external systems when stage changes
3. **Custom stages** - Allow defining your own stages
4. **Stage analytics** - Average time in each stage, conversion rates per stage
5. **Bulk operations** - Move multiple leads to a stage at once

---

## Summary

**What You Can Do Now:**

1. ✅ See every lead's current stage in real-time
2. ✅ Get all leads in any specific stage
3. ✅ Track lead data automatically (name, phone, course, etc.)
4. ✅ Get conversion statistics
5. ✅ Manually update stages when needed
6. ✅ See complete history of stage changes
7. ✅ All of this with API key security

**What Changed:**

- ✏️ `core/memory.py` - Added 8 new methods for stage tracking
- ✏️ `core/agent.py` - Added automatic lead data extraction
- ✏️ `app.py` - Added 4 new API endpoints
- ✏️ `ChatResponse` - Now includes stage and lead_data

**What Stayed the Same:**

- ✅ All existing endpoints still work
- ✅ Old conversations are automatically migrated
- ✅ No breaking changes to existing code
- ✅ Performance is still fast

---

**Questions?** Check the main PROJECT_BRAIN.md for deep technical details.
