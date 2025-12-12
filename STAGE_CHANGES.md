# Stage System Update (Quick Notes)

- Added lightweight extraction so the agent auto-updates lead data from chat text:
  - Names from phrases like “my name is …” or “I am …”
  - Phone numbers (digits with optional +, spaces, or dashes)
  - Education level keywords (matric/inter, O/A Levels, bachelors/masters, ACCA/CA/CIMA)
- Course detection still runs on common course names (CTA, ACCA, UK/US/UAE Taxation, finance/accounting).
- Stage is derived automatically from collected fields (NEW → NAME_COLLECTED → COURSE_SELECTED → EDUCATION_COLLECTED → GOAL_COLLECTED → DEMO_SHARED → ENROLLED; LOST is manual).
- Conversation list API now returns stage info (`stage`, `stage_updated_at`) alongside summary/turn counts.
- All stage and lead data stay in `memory_db/conversations_metadata.json` and are exposed in `/chat`, stage endpoints, and stats.
