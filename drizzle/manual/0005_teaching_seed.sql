-- Seed the initial commissioned teaching topics (docs spec §4.1.3) and create
-- the PRIVATE storage bucket for uploaded teaching materials.
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0005_teaching_seed.sql
-- Safe to re-run.

-- Topics are admin-editable rows; this seed only inserts them once.
insert into teaching_topics (title, description, format, status, sort_order)
select * from (values
  (
    'How to publish a systematic or literature review',
    'Framing an answerable question, searching properly, screening and extraction, PRISMA, quality assessment, writing up, choosing a journal, handling reviewers.',
    '8 sessions, 45 min, live',
    'accepting_submissions'::teaching_topic_status,
    1
  ),
  (
    'Common acute presentations in the emergency department',
    'Structured approach to chest pain, breathlessness, the unconscious patient, abdominal pain, sepsis, trauma primary survey. Recognition, initial management, escalation.',
    '10 sessions, 45 min, live',
    'accepting_submissions'::teaching_topic_status,
    2
  ),
  (
    'Clinical audit and quality improvement: running a complete cycle',
    'Choosing a standard, registering the audit, collecting data, presenting findings, implementing change, and closing the loop with a re-audit.',
    '6 sessions, 45 min, live',
    'accepting_submissions'::teaching_topic_status,
    3
  )
) as seed(title, description, format, status, sort_order)
where not exists (select 1 from teaching_topics);

-- Private bucket: no public read policy and no user policies at all — only the
-- service role touches it. Uploaded course material is reviewed by the admin
-- and the approving clinician, never served from a predictable public URL.
insert into storage.buckets (id, name, public)
values ('teaching-materials', 'teaching-materials', false)
on conflict (id) do update set public = false;
