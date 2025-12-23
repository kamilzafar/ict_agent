-- Supabase Database Schema for ICT Agent
-- Create these tables manually in your Supabase project
-- All queries are optimized for <10ms performance with proper indexes
-- All column types are TEXT for consistency

-- ============================================================================
-- Enable Trigram Extension (for fuzzy text search) - Run this first
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- 1) Course Details Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS course_details (
  course_name TEXT,
  course_description TEXT,
  course_benefits TEXT,
  course_start_date_or_last_enrollment_date TEXT,
  professor_name TEXT,
  course_duration TEXT,
  course_fee_physical TEXT,
  course_fee_online TEXT,
  course_fee_hibernate TEXT,
  enrollment_status TEXT,
  mode_of_courses TEXT,
  online_available TEXT,
  physical_available TEXT,
  location_islamabad TEXT,
  location_karachi TEXT,
  location_lahore TEXT
);

-- Indexes for fast course name lookups (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_course_details_course_name ON course_details USING gin (course_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_course_details_professor ON course_details USING gin (professor_name gin_trgm_ops);

-- ============================================================================
-- 2) Course Links Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS course_links (
  course_name TEXT,
  course_link TEXT,
  demo_link TEXT,
  pdf_link TEXT
);

-- Index for fast course name lookups (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_course_links_course_name ON course_links USING gin (course_name gin_trgm_ops);

-- ============================================================================
-- 3) FAQs Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS faqs (
  faq TEXT,
  course_name TEXT,
  question TEXT,
  answer TEXT
);

-- Full-text search index for questions and answers (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_faqs_question_answer ON faqs USING gin (to_tsvector('english', question || ' ' || answer));
CREATE INDEX IF NOT EXISTS idx_faqs_course_name ON faqs USING gin (course_name gin_trgm_ops);

-- ============================================================================
-- 4) About Professor Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS about_professor (
  instructor_id TEXT,
  full_name TEXT,
  display_name_for_students TEXT,
  qualifications TEXT,
  total_years_of_experience TEXT,
  specializations TEXT,
  courses_currently_teaching TEXT,
  course_in_which_city TEXT,
  certifications TEXT,
  short_bio_for_agent TEXT,
  detailed_bio_for_website TEXT
);

-- Indexes for fast lookups (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_professor_full_name ON about_professor USING gin (full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_professor_courses ON about_professor USING gin (courses_currently_teaching gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_professor_instructor_id ON about_professor (instructor_id);

-- ============================================================================
-- 5) Company Info Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS company_info (
  field_name TEXT,
  field_value TEXT,
  notes TEXT
);

-- Index for fast field name lookups (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_company_info_field_name ON company_info (field_name);

-- ============================================================================
-- 6) Leads Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS leads (
  lead_name TEXT,
  phone_number TEXT,
  course_selected TEXT,
  background TEXT,
  why_they_want_course TEXT,
  label TEXT,
  status TEXT,
  timestamp TEXT,
  have_sent_demo_link TEXT,
  have_done_the_call TEXT
);

-- Indexes for fast lookups (optimized for <10ms)
CREATE INDEX IF NOT EXISTS idx_leads_phone_number ON leads (phone_number);
CREATE INDEX IF NOT EXISTS idx_leads_course_selected ON leads USING gin (course_selected gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_leads_timestamp ON leads (timestamp);

-- ============================================================================
-- Row Level Security (RLS) - Optional
-- ============================================================================
-- Enable RLS if you want to restrict access:
-- ALTER TABLE course_details ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE course_links ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE faqs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE about_professor ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE company_info ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

-- Create policies (example - adjust based on your needs):
-- CREATE POLICY "Allow public read access" ON course_details FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON course_links FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON faqs FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON about_professor FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON company_info FOR SELECT USING (true);
-- CREATE POLICY "Allow insert for leads" ON leads FOR INSERT WITH CHECK (true);
