"""Check what course names are actually in Supabase."""
import os
from dotenv import load_dotenv
from core.supabase_service import SupabaseService

load_dotenv()

# Initialize Supabase
supabase = SupabaseService(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

print("=" * 80)
print("ACTUAL COURSE NAMES IN SUPABASE DATABASE:")
print("=" * 80)

# Get all courses
try:
    response = supabase.client.table("course_details").select("course_name,course_fee_physical").execute()

    if response.data:
        print(f"\nFound {len(response.data)} courses:\n")
        for i, course in enumerate(response.data, 1):
            name = course.get('course_name', 'N/A')
            fee = course.get('course_fee_physical', 'N/A')
            print(f"{i}. Name: {name}")
            print(f"   Fee: {fee}")
            print()
    else:
        print("No courses found in database!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("=" * 80)
print("\nRECOMMENDATION:")
print("=" * 80)
print("Update your prompt.txt course list (line ~318) to use these EXACT names.")
print("Or clean the Supabase data to use simple names like 'CTA', 'USA Taxation', etc.")
