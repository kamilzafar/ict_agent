"""Test Supabase access after RLS fix."""
from core.supabase_service import SupabaseService
import os
from dotenv import load_dotenv

load_dotenv()

supabase = SupabaseService(
    supabase_url=os.getenv('SUPABASE_URL'),
    supabase_key=os.getenv('SUPABASE_KEY')
)

print('Testing Supabase table access...')
print('='*70)

tables = ['course_details', 'course_links', 'about_professor', 'company_info', 'faqs', 'leads']

for table in tables:
    try:
        response = supabase.client.table(table).select('*').limit(1).execute()
        if response.data:
            print(f'✓ {table}: {len(response.data)} row(s) - ACCESS OK')
        else:
            print(f'× {table}: 0 rows - EMPTY or NO ACCESS')
    except Exception as e:
        print(f'× {table}: ERROR - {str(e)[:60]}')

print('\n' + '='*70)
print('If you see "0 rows" above, RLS is blocking access.')
print('Follow the solutions above to fix it.')
