"""Direct test of fetch_course_details tool."""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import services
from core.supabase_service import SupabaseService
from tools.supabase_tools import create_supabase_tools

# Initialize Supabase
print("Initializing Supabase...")
supabase_service = SupabaseService(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)
print("[OK] Supabase initialized\n")

# Create tools
print("Creating tools...")
tools = create_supabase_tools(supabase_service)
print(f"[OK] Created {len(tools)} tools\n")

# Find fetch_course_details tool
fetch_course_details = None
for tool in tools:
    if tool.name == "fetch_course_details":
        fetch_course_details = tool
        break

if not fetch_course_details:
    print("ERROR: fetch_course_details tool not found!")
    sys.exit(1)

print(f"[OK] Found fetch_course_details tool\n")

# Test the tool with different course names
test_courses = [
    "CTA",
    "Certified Tax Advisor",
    "USA Taxation",
    "Transfer Pricing"
]

for course in test_courses:
    print(f"=" * 70)
    print(f"Testing: {course}")
    print(f"=" * 70)

    try:
        result = fetch_course_details.invoke({"course_name": course})
        print(result)
        print()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        print()
