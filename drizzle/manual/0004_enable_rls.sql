-- Enable Row Level Security on every public table (deny-all backstop).
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0004_enable_rls.sql
-- Safe to re-run.
--
-- All reads/writes go through server actions (service_role, which bypasses
-- RLS), so no policies are needed: with RLS on and no policies, the public
-- anon/authenticated API and Realtime broadcasts return nothing. If a client
-- component ever needs direct Supabase access (e.g. live chat), add an
-- explicit policy for that table here.

alter table public.app_errors enable row level security;
alter table public.applications enable row level security;
alter table public.availability_listings enable row level security;
alter table public.listing_contacts enable row level security;
alter table public.contact_messages enable row level security;
alter table public.badges enable row level security;
alter table public.conversation_participants enable row level security;
alter table public.conversations enable row level security;
alter table public.listing_questions enable row level security;
alter table public.messages enable row level security;
alter table public.notifications enable row level security;
alter table public.profile_certifications enable row level security;
alter table public.profile_skills enable row level security;
alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.publications enable row level security;
alter table public.reports enable row level security;
alter table public.reviews enable row level security;
alter table public.saved_projects enable row level security;
alter table public.skills enable row level security;
alter table public.teaching_topics enable row level security;
alter table public.teaching_submissions enable row level security;
alter table public.teaching_submission_revisions enable row level security;
alter table public.user_badges enable row level security;
alter table public.verifications enable row level security;
