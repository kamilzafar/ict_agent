"""Upload course details from CSV to Supabase."""
import os
import csv
from dotenv import load_dotenv
from core.supabase_service import SupabaseService

load_dotenv()

# Initialize Supabase
print("Connecting to Supabase...")
supabase = SupabaseService(
    supabase_url=os.getenv("SUPABASE_URL"),
    supabase_key=os.getenv("SUPABASE_KEY")
)

# Read CSV file
print("\nReading course_details_rows.csv...")
courses = []
with open('course_details_rows.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    courses = list(reader)

print(f"Found {len(courses)} courses in CSV")

# Check current database state
print("\nChecking current database...")
existing = supabase.client.table('course_details').select('course_name').execute()
print(f"Current courses in database: {len(existing.data)}")

if existing.data:
    print("\nWARNING: Database already has courses. Options:")
    print("1. Delete all and re-upload (recommended if data is outdated)")
    print("2. Skip upload (keep existing data)")
    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "1":
        print("\nDeleting existing courses...")
        # Delete all existing courses
        for course in existing.data:
            supabase.client.table('course_details').delete().eq('course_name', course['course_name']).execute()
        print("✓ Deleted all existing courses")
    else:
        print("Skipping upload. Exiting...")
        exit(0)

# Upload courses
print(f"\nUploading {len(courses)} courses to Supabase...")
success_count = 0
error_count = 0

for i, course in enumerate(courses, 1):
    try:
        # Clean empty strings to None
        cleaned_course = {k: (v if v != '' else None) for k, v in course.items()}

        # Insert course
        result = supabase.client.table('course_details').insert(cleaned_course).execute()
        success_count += 1
        print(f"✓ {i}/{len(courses)}: {course.get('course_name', 'Unknown')}")
    except Exception as e:
        error_count += 1
        print(f"✗ {i}/{len(courses)}: {course.get('course_name', 'Unknown')} - Error: {e}")

print("\n" + "="*70)
print(f"Upload Complete!")
print(f"  ✓ Success: {success_count}")
print(f"  ✗ Errors: {error_count}")
print("="*70)

# Verify upload
print("\nVerifying upload...")
final_courses = supabase.client.table('course_details').select('course_name').execute()
print(f"Total courses in database: {len(final_courses.data)}")

if final_courses.data:
    print("\nCourses in database:")
    for i, course in enumerate(final_courses.data, 1):
        print(f"  {i}. {course['course_name']}")
