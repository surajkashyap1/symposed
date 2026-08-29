-- =====================================================================
-- Research Platform — Database Schema (PostgreSQL / Supabase)
-- =====================================================================
-- MVP scope. Target: Next.js + Drizzle ORM, Supabase EU/London region.
--
-- Auth note: Supabase manages the `auth.users` table for you. We keep a
-- public `profiles` table (1:1 with auth.users) for app-facing data.
--
-- Security note: For the MVP, do business logic in Next.js server actions
-- using the Supabase service key (server-side only). Add Row-Level
-- Security (RLS) policies as a backstop on sensitive tables before launch.
-- =====================================================================


-- ----------------------------- ENUMS ---------------------------------

create type career_stage as enum (
  'medical_student','dental_student','nursing_student','other_student',
  'foundation_doctor','junior_doctor','registrar','consultant',
  'dentist','qualified_nurse','professor','postdoc','staff_grade','other'
);

create type experience_level as enum (
  'beginner_welcome','some_experience','experienced_only'
);

create type project_type as enum (
  'audit','systematic_review','literature_review','case_study',
  'retrospective','prospective_study','poster','teaching','other'
);

create type project_status as enum ('draft','open','in_progress','closed','completed');

create type application_status as enum
  ('pending','shortlisted','accepted','rejected','withdrawn');

create type verification_type as enum
  ('university_email','nhs_email','linkedin','manual','login_email');
create type verification_status as enum ('pending','verified','rejected');

create type conversation_type as enum ('application_dm','project_chat');
create type review_direction as enum ('supervisor_to_member','member_to_supervisor');
create type notification_type as enum
  ('application','message','review','match','system');


-- --------------------------- PROFILES --------------------------------

create table profiles (
  id                  uuid primary key references auth.users(id) on delete cascade,
  full_name           text not null,
  email               text not null unique,
  avatar_url          text,
  summary             text,                       -- short statement about interests
  university          text,
  career_stage        career_stage not null default 'other',
  specialty           text,
  contact_phone       text,                        -- private; revealed to the counterparty only on acceptance, never on a public profile
  is_verified         boolean not null default false,  -- any verification passed
  email_confirmed_at  timestamptz,                 -- login email confirmed (app-side)
  can_supervise       boolean not null default false,  -- eligible as project supervisor
  is_new_researcher   boolean not null default true,   -- no completed projects yet
  reliability_score   numeric(3,2),                -- 0.00-5.00, aggregated; null until rated
  availability        text,                        -- e.g. hours/week, free text for MVP
  availability_hours_per_week int,
  preferred_project_types text,                    -- comma-separated project types sought
  preferred_specialties text,                      -- comma-separated specialties sought
  profile_completeness int not null default 0,     -- 0-100, computed app-side
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);


-- Skills (normalised so they're filterable) -------------------------
create table skills (
  id    serial primary key,
  name  text not null unique          -- 'coding','data analysis','literature review',...
);

create table profile_skills (
  profile_id  uuid references profiles(id) on delete cascade,
  skill_id    int  references skills(id)   on delete cascade,
  primary key (profile_id, skill_id)
);

create table profile_certifications (
  id          uuid primary key default gen_random_uuid(),
  profile_id  uuid not null references profiles(id) on delete cascade,
  name        text not null,
  proof_url   text,
  created_at  timestamptz not null default now()
);

create index profile_certifications_profile_idx
  on profile_certifications (profile_id);


-- Existing publications shown on a profile --------------------------
create table publications (
  id          uuid primary key default gen_random_uuid(),
  profile_id  uuid not null references profiles(id) on delete cascade,
  title       text not null,
  url         text,
  year        int,
  created_at  timestamptz not null default now()
);


-- Verification attempts (university / NHS email / LinkedIn) ---------
create table verifications (
  id           uuid primary key default gen_random_uuid(),
  profile_id   uuid not null references profiles(id) on delete cascade,
  type         verification_type not null,
  status       verification_status not null default 'pending',
  detail       text,                   -- e.g. domain checked, linkedin url
  verified_at  timestamptz,
  created_at   timestamptz not null default now()
);


-- --------------------------- PROJECTS --------------------------------

create table projects (
  id                   uuid primary key default gen_random_uuid(),
  owner_id             uuid not null references profiles(id) on delete cascade, -- lister
  supervisor_id        uuid references profiles(id),   -- null if not yet established
  title                text not null,
  description          text not null,
  project_type         project_type not null,
  experience_level     experience_level not null,
  specialty            text,
  role_category        text,                  -- 'data extraction','lit screening',...
  is_beginner_friendly boolean not null default false,
  positions_available  int not null default 1,
  status               project_status not null default 'open',
  application_deadline date,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);

create index projects_status_idx       on projects (status);
create index projects_experience_idx   on projects (experience_level);
create index projects_specialty_idx    on projects (specialty);


-- ------------------------- APPLICATIONS ------------------------------
-- Standardised form: motivation, suitability, skills (word limits in app).
-- Application limit (3 / rolling 7 days, +3 / 2 weeks if user posted a
-- project with a validated supervisor email) is enforced in app logic by
-- counting rows in a time window — see applications_applicant_time_idx.

create table applications (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  applicant_id  uuid not null references profiles(id) on delete cascade,
  status        application_status not null default 'pending',
  motivation    text not null,        -- reasons for applying / interests
  suitability   text not null,        -- why suitable for the role
  hours_per_week int,                  -- weekly time the applicant can dedicate
  skills_summary text,                -- relevant skills
  created_at    timestamptz not null default now(),
  unique (project_id, applicant_id)   -- one application per project per user
);

create index applications_applicant_time_idx on applications (applicant_id, created_at);
create index applications_project_idx        on applications (project_id);


-- --------------------- PUBLIC Q&A ON LISTINGS ------------------------
-- Public questions anyone can see, before applying.

create table listing_questions (
  id           uuid primary key default gen_random_uuid(),
  project_id   uuid not null references projects(id) on delete cascade,
  asker_id     uuid not null references profiles(id) on delete cascade,
  question     text not null,
  answer       text,
  answered_at  timestamptz,
  created_at   timestamptz not null default now()
);


-- ---------------------- PRIVATE MESSAGING ----------------------------
-- application_dm  = one short message after applying (limit in app layer)
-- project_chat    = unlimited chat after acceptance/shortlist

create table conversations (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid references projects(id) on delete cascade,
  type        conversation_type not null,
  created_at  timestamptz not null default now()
);

create table conversation_participants (
  conversation_id  uuid references conversations(id) on delete cascade,
  profile_id       uuid references profiles(id) on delete cascade,
  primary key (conversation_id, profile_id)
);

create table messages (
  id               uuid primary key default gen_random_uuid(),
  conversation_id  uuid not null references conversations(id) on delete cascade,
  sender_id        uuid not null references profiles(id) on delete cascade,
  body             text not null,
  read_at          timestamptz,
  created_at       timestamptz not null default now()
);

create index messages_conversation_idx on messages (conversation_id, created_at);


-- ----------------------- REVIEWS / REPUTATION ------------------------
-- supervisor_to_member: reliability, communication, contribution, deadlines
-- member_to_supervisor: communication, supervision, teaching, fair authorship
-- Only project supervisors can review members (enforce in app/RLS).

create table reviews (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  reviewer_id     uuid not null references profiles(id) on delete cascade,
  reviewee_id     uuid not null references profiles(id) on delete cascade,
  direction       review_direction not null,
  rating_overall  numeric(2,1) not null,   -- 1.0-5.0
  reliability     int,
  communication   int,
  contribution    int,
  meets_deadlines int,
  supervision     int,
  teaching        int,
  fair_authorship int,
  comment         text,
  is_anonymous    boolean not null default false,
  created_at      timestamptz not null default now(),
  unique (project_id, reviewer_id, reviewee_id)
);

create index reviews_reviewee_idx on reviews (reviewee_id);


-- --------------------------- BADGES ----------------------------------
-- e.g. research_mentor (6-month validity), new_researcher,
--      top_mentor, project_lead

create table badges (
  id           serial primary key,
  code         text not null unique,
  name         text not null,
  description  text
);

create table user_badges (
  id          uuid primary key default gen_random_uuid(),
  profile_id  uuid not null references profiles(id) on delete cascade,
  badge_id    int  not null references badges(id) on delete cascade,
  awarded_at  timestamptz not null default now(),
  expires_at  timestamptz,             -- e.g. Research Mentor valid 6 months
  unique (profile_id, badge_id)
);


-- ------------------------ NOTIFICATIONS ------------------------------

create table notifications (
  id          uuid primary key default gen_random_uuid(),
  profile_id  uuid not null references profiles(id) on delete cascade,
  type        notification_type not null,
  title       text not null,
  body        text,
  link        text,
  read_at     timestamptz,
  created_at  timestamptz not null default now()
);

create index notifications_unread_idx on notifications (profile_id, read_at);


-- --------------------- SAVED / BOOKMARKED ----------------------------

create table saved_projects (
  profile_id  uuid references profiles(id) on delete cascade,
  project_id  uuid references projects(id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (profile_id, project_id)
);

-- ----------------------- TRUST & SAFETY ------------------------------

create type report_target_type as enum ('project','question','profile','review');
create type report_status as enum ('open','actioned','dismissed');

-- User reports about content or conduct; reviewed on /admin.
create table reports (
  id           uuid primary key default gen_random_uuid(),
  reporter_id  uuid not null references profiles(id) on delete cascade,
  target_type  report_target_type not null,
  target_id    uuid not null,
  reason       text not null,
  status       report_status not null default 'open',
  resolved_at  timestamptz,
  created_at   timestamptz not null default now()
);

create index reports_status_idx on reports (status, created_at);

-- Contact-form submissions (feedback, complaints, data protection requests).
create table contact_messages (
  id          uuid primary key default gen_random_uuid(),
  sender_id   uuid references profiles(id) on delete set null,
  email       text,
  topic       text not null,
  message     text not null,
  created_at  timestamptz not null default now()
);

-- ------------------------ TEACHING PLATFORM --------------------------

-- Commissioned topics on /teach: admin-editable rows, never hardcoded.
create type teaching_topic_status as enum
  ('accepting_submissions', 'under_review', 'filled');

create table teaching_topics (
  id          serial primary key,
  title       text not null,
  description text not null,
  format      text not null,
  deadline    date,
  status      teaching_topic_status not null default 'accepting_submissions',
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now()
);

-- Rolling review; publication is gated on direct clinician confirmation via
-- the emailed token link (applicant-forwarded confirmations are forgeable).
create type teaching_submission_status as enum
  ('submitted', 'under_review', 'revisions_requested', 'approved',
   'clinician_verification', 'scheduled', 'delivered', 'declined');

create type clinician_verification_status as enum
  ('pending', 'confirmed', 'declined');

create type teaching_delivery_format as enum
  ('live_with_recordings', 'live_only', 'recorded_only');

create table teaching_submissions (
  id                     uuid primary key default gen_random_uuid(),
  profile_id             uuid not null references profiles(id) on delete cascade,
  topic_id               integer references teaching_topics(id) on delete set null,
  applicant_gmc_number   text,
  title                  text not null,
  description            text not null,
  learning_objectives    text[] not null,   -- 3–5 entries
  target_audience        text[] not null,
  sessions_plan          text not null,
  delivery_format        teaching_delivery_format not null,
  start_availability     text not null,
  relevant_experience    text not null,
  materials_path         text not null,     -- private bucket path, signed URLs only
  materials_filename     text not null,
  status                 teaching_submission_status not null default 'submitted',
  admin_feedback         text,
  clinician_name         text not null,
  clinician_grade        text not null,
  clinician_specialty    text not null,
  clinician_institution  text not null,
  clinician_gmc_number   text not null,
  clinician_email        text not null,
  clinician_token        text not null unique,
  clinician_status       clinician_verification_status not null default 'pending',
  clinician_responded_at timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index teaching_submissions_profile_idx on teaching_submissions (profile_id);
create index teaching_submissions_status_idx on teaching_submissions (status, created_at);

-- Pre-edit payload snapshotted on every resubmission (version history).
create table teaching_submission_revisions (
  id            uuid primary key default gen_random_uuid(),
  submission_id uuid not null references teaching_submissions(id) on delete cascade,
  payload       text not null,  -- JSON snapshot of the replaced version
  created_at    timestamptz not null default now()
);

create index teaching_submission_revisions_submission_idx
  on teaching_submission_revisions (submission_id);

-- -------------- AVAILABLE FOR PROJECTS (reverse board) ---------------

-- A user advertising themselves to project listers. One listing per user;
-- editing replaces. Expiry (60 days) is enforced at query time
-- (status = 'active' and expires_at > now()); renewal emails are best-effort.
create type availability_listing_status as enum
  ('active', 'found_project', 'removed');

create table availability_listings (
  id                    uuid primary key default gen_random_uuid(),
  profile_id            uuid not null unique references profiles(id) on delete cascade,
  headline              text not null,
  display_initials_only boolean not null default false,
  show_institution      boolean not null default true,
  region                text,
  specialties           text,           -- comma-separated, max 3
  skills                text[] not null, -- values from SKILLS_OFFERED
  hours_per_week        integer,
  available_from        date,
  previous_publications text,
  looking_for           text not null,
  status                availability_listing_status not null default 'active',
  expires_at            timestamptz not null,
  renewal_emailed_at    timestamptz,
  found_project_at      timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create index availability_listings_board_idx
  on availability_listings (status, expires_at, updated_at);

-- Relay messages sent to a listing owner ("Get in touch"). Logged both
-- sides for abuse investigation; email addresses are never exposed.
create table listing_contacts (
  id           uuid primary key default gen_random_uuid(),
  listing_id   uuid not null references availability_listings(id) on delete cascade,
  sender_id    uuid not null references profiles(id) on delete cascade,
  recipient_id uuid not null references profiles(id) on delete cascade,
  body         text not null,
  created_at   timestamptz not null default now()
);

create index listing_contacts_sender_time_idx on listing_contacts (sender_id, created_at);
create index listing_contacts_listing_idx on listing_contacts (listing_id);

-- --------------------- ERROR MONITORING ------------------------------

-- Unhandled server errors captured by instrumentation.onRequestError,
-- shown on /admin. Rows older than 30 days are pruned on insert.
create table app_errors (
  id          uuid primary key default gen_random_uuid(),
  message     text not null,
  digest      text,
  stack       text,
  path        text,
  method      text,
  route_path  text,
  route_type  text,
  created_at  timestamptz not null default now()
);

create index app_errors_created_idx on app_errors (created_at);

-- =====================================================================
-- DEFERRED (do NOT build for MVP — add tables when you reach these):
--   • subscriptions / pricing tiers (Stripe)        -> Pricing model §8
--   • ads / featured listings                        -> §8, §14
--   • mentor admin tools (checklists, reminders)     -> §7 admin
--   • leaderboard snapshots                          -> §11
-- =====================================================================

-- --------------------- ROW LEVEL SECURITY ----------------------------
-- Deny-all backstop: RLS is enabled on every table with NO policies.
-- All access goes through server actions (service_role bypasses RLS);
-- the public anon/authenticated API and Realtime therefore return nothing.
-- Applied via drizzle/manual/0004_enable_rls.sql — if you add a table,
-- add it there too and re-apply.
