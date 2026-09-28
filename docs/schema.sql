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
  ref_code            text,                        -- §9 first-touch channel, set once at signup
  listing_nudge_opt_out boolean not null default false, -- §8.5 nudge-email opt-out
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
  source_guide_order_id uuid, -- §8.4 auto-drafted from a guide (FK added after guide_orders below)
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

-- ------------------------ PUBLICATION GUIDES -------------------------

-- Paid, bespoke, human-verified guides (spec §3). Proforma completed before
-- payment; orders become 'paid' only on the Stripe webhook.
create type guide_order_status as enum
  ('submitted', 'paid', 'in_progress', 'delivered', 'refunded');

create table guide_orders (
  id                       uuid primary key default gen_random_uuid(),
  profile_id               uuid not null references profiles(id) on delete cascade,
  proforma                 text not null,   -- full JSON payload
  full_name                text not null,
  email                    text not null,
  status                   guide_order_status not null default 'submitted',
  discount_applied         boolean not null default false,
  price_at_checkout_pence  integer,
  price_paid_pence         integer,
  checkout_started_at      timestamptz,
  stripe_session_id        text,
  stripe_payment_intent_id text,
  consent_immediate_at     timestamptz,     -- immediate-performance waiver
  consent_terms_at         timestamptz,
  consent_ip               text,
  ip_country               text,            -- location evidence, keep >= 10y
  billing_country          text,
  card_country             text,
  country_mismatch         boolean not null default false,
  verified_by              text,            -- human-involvement record (§7.5)
  verified_at              timestamptz,
  verification_note        text,
  paid_at                  timestamptz,
  delivered_at             timestamptz,
  overdue_alerted_at       timestamptz,
  listing_nudge_10_at      timestamptz,     -- §8.5 first publish-your-listing nudge
  listing_nudge_30_at      timestamptz,     -- §8.5 second/final nudge
  review_token             text unique,
  review_requested_at      timestamptz,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

-- §8.4 FK (declared here because projects is defined before guide_orders).
alter table projects
  add constraint projects_source_guide_order_id_fkey
  foreign key (source_guide_order_id) references guide_orders(id) on delete set null;

create index guide_orders_profile_idx on guide_orders (profile_id);
create index guide_orders_status_idx on guide_orders (status, created_at);
create index guide_orders_session_idx on guide_orders (stripe_session_id);

create table guide_order_files (
  id           uuid primary key default gen_random_uuid(),
  order_id     uuid not null references guide_orders(id) on delete cascade,
  path         text not null,   -- private bucket; authenticated route only
  filename     text not null,
  content_type text not null,
  created_at   timestamptz not null default now()
);

create index guide_order_files_order_idx on guide_order_files (order_id);

-- Single row (id = 1), admin-editable. Prices are pence and are the TOTAL
-- payable (DMCC drip-pricing ban).
-- Three-band price ladder (amendment §2): first `free_quantity` guides free,
-- next `intro_quantity` at `intro_price_pence` (the £25 tier), then
-- `standard_price_pence` (£45). `payments_enabled` is the launch toggle: while
-- OFF, checkout is skipped and requests go straight to the queue at no charge.
create table guide_pricing_config (
  id                   integer primary key default 1,
  standard_price_pence integer not null default 4500,
  intro_price_pence    integer not null default 2500,
  intro_quantity       integer not null default 25,
  free_quantity        integer not null default 25,
  payments_enabled     boolean not null default false,
  blocked_countries    text[] not null,  -- ISO alpha-2, default {IN,PK}
  updated_at           timestamptz not null default now()
);

create type guide_review_status as enum
  ('pending', 'approved', 'rejected', 'removed');

create table guide_reviews (
  id                   uuid primary key default gen_random_uuid(),
  order_id             uuid references guide_orders(id) on delete set null,
  reviewer_name        text not null,
  reviewer_role        text not null,
  reviewer_institution text,
  rating               integer not null,
  body                 text not null,
  guide_topic          text,
  complimentary_guide  boolean not null default false,  -- DMCC disclosure badge
  status               guide_review_status not null default 'pending',
  published_at         timestamptz,
  created_at           timestamptz not null default now()
);

create index guide_reviews_status_idx on guide_reviews (status, published_at);

-- ----------------------- GUIDE PIPELINE (build spec §5) --------------------
-- Written by the Python guide pipeline, read by the admin verification screen.
-- No include/exclude boolean anywhere: papers carry a visible graded status.

create type guide_run_status as enum ('running', 'found', 'needs_contact', 'failed');

create table guide_runs (
  id                uuid primary key default gen_random_uuid(),
  order_id          uuid references guide_orders(id) on delete cascade,
  status            guide_run_status not null default 'running',
  title             text,
  publication_type  text,
  axis              text,
  contact_reason    text,             -- why to email the user (needs_contact)
  cost_usd          numeric(10,4),
  pipeline_version  text,
  results           jsonb,            -- full results record
  metrics           jsonb,            -- per-guide feedback record
  guide_docx        bytea,            -- draft guide for the reviewer
  started_at        timestamptz not null default now(),
  finished_at       timestamptz
);
create index guide_runs_order_idx on guide_runs (order_id, started_at);

create table guide_run_candidates (
  id                uuid primary key default gen_random_uuid(),
  run_id            uuid not null references guide_runs(id) on delete cascade,
  title             text not null,
  normalized_title  text not null,
  axis              text not null,
  batch             integer not null,
  outcome           text not null,    -- pass | flag | downgrade | reject
  gates             jsonb not null,   -- each gate: outcome, value, threshold
  score             jsonb,
  eligible_studies  integer,
  recent_reviews    integer,
  created_at        timestamptz not null default now()
);
create index guide_run_candidates_run_idx on guide_run_candidates (run_id);
create index guide_run_candidates_title_idx on guide_run_candidates (normalized_title);

-- A question offered to one customer is never offered to another (spec §5).
create table guide_title_registry (
  normalized_title  text primary key,
  title             text not null,
  first_run_id      uuid references guide_runs(id) on delete set null,
  order_id          uuid references guide_orders(id) on delete set null,
  status            text not null default 'offered',  -- offered | approved | rejected
  created_at        timestamptz not null default now()
);

create table guide_searches (
  id            uuid primary key default gen_random_uuid(),
  run_id        uuid not null references guide_runs(id) on delete cascade,
  source        text not null,
  query         text not null,
  result_count  integer,
  run_at        timestamptz not null
);
create index guide_searches_run_idx on guide_searches (run_id);

create table guide_screened_papers (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references guide_runs(id) on delete cascade,
  identifier      text not null,      -- PMID, or Europe PMC id for preprints
  id_type         text not null default 'PMID',
  doi             text,
  title           text not null,
  year            integer,
  journal         text,
  status          text not null,      -- likely eligible | likely ineligible | unclear, check full text
  reason          text not null,
  evidence_basis  text not null,      -- abstract only | full text (...)
  attributes      jsonb
);
create index guide_screened_papers_run_idx on guide_screened_papers (run_id, status);

-- The PROSPERO check record (spec §3.5): retain permanently.
create table guide_prospero_checks (
  id                   uuid primary key default gen_random_uuid(),
  run_id               uuid not null references guide_runs(id) on delete cascade,
  title                text not null,
  search_terms         text not null,
  checked_on           date not null,
  mirror_covered_to    date not null,
  mirror_refreshed_at  timestamptz,
  verdict              text not null,  -- registered | review | clear
  matches              jsonb not null
);
create index guide_prospero_checks_run_idx on guide_prospero_checks (run_id);

create table guide_tie_breaks (
  id               uuid primary key default gen_random_uuid(),
  run_id           uuid not null references guide_runs(id) on delete cascade,
  candidates       jsonb not null,
  model_choice     integer not null,
  rationale        jsonb not null,
  summary          text,
  override_choice  integer,
  override_reason  text,
  created_at       timestamptz not null default now()
);
create index guide_tie_breaks_run_idx on guide_tie_breaks (run_id);

create type guide_verification_action as enum
  ('approved', 'edited_and_approved', 'rejected');

-- Stage 6: who verified, when, what changed, the outcome, live PROSPERO date.
create table guide_verifications (
  id                        uuid primary key default gen_random_uuid(),
  run_id                    uuid not null references guide_runs(id) on delete cascade,
  order_id                  uuid references guide_orders(id) on delete set null,
  reviewer                  text not null,
  action                    guide_verification_action not null,
  edited_title              text,
  notes                     text,
  live_prospero_checked_on  date,
  created_at                timestamptz not null default now()
);
create index guide_verifications_run_idx on guide_verifications (run_id);

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
-- MEMBER BENEFITS + ATTRIBUTION (amendment §8 / §9)
-- =====================================================================

-- §8: single-row config for the tunables the amendment keeps configurable.
create table platform_config (
  id                     integer primary key default 1,
  credits_standard       int not null default 3,   -- §8.9 no live listing
  credits_lister         int not null default 6,   -- §8.9 has a live listing
  credits_guide_lister   int not null default 9,   -- §8.9 live listing from a guide
  support_allowance      int not null default 3,   -- §8.8 bounded direct support
  support_response_days  int not null default 7,
  vest_listing_days      int not null default 0,   -- §8.7 anti-gaming, 0 = off
  updated_at             timestamptz not null default now()
);

-- §8.8 bounded direct-support questions; allowance enforced in app logic.
create table support_questions (
  id          uuid primary key default gen_random_uuid(),
  profile_id  uuid not null references profiles(id) on delete cascade,
  order_id    uuid references guide_orders(id) on delete set null,
  question    text not null,
  answer      text,
  answered_at timestamptz,
  created_at  timestamptz not null default now()
);
create index support_questions_profile_idx on support_questions (profile_id, created_at);

-- §9.3 administrator-managed referral codes (lowercase, alphanumeric+hyphens).
create table referral_codes (
  id         serial primary key,
  code       text not null unique,
  label      text not null,
  created_at timestamptz not null default now()
);

-- §9.2 first-touch visit log (one row per new visitor, "direct" when no code).
create table attribution_visits (
  id         uuid primary key default gen_random_uuid(),
  code       text not null,
  created_at timestamptz not null default now()
);
create index attribution_visits_code_idx on attribution_visits (code, created_at);

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
