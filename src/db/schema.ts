// =====================================================================
// Drizzle schema — mirror of docs/schema.sql
// =====================================================================
// Note: `profiles.id` is intended to reference Supabase's `auth.users(id)`.
// Drizzle can't easily express a cross-schema FK to `auth`, so that link is
// enforced at the database level (see docs/schema.sql) / via a trigger that
// inserts a profile row on signup. Here we keep `id` as a uuid PK.
// =====================================================================

import {
  pgTable,
  pgEnum,
  uuid,
  text,
  boolean,
  integer,
  serial,
  numeric,
  date,
  timestamp,
  primaryKey,
  unique,
  index,
  jsonb,
  customType,
} from "drizzle-orm/pg-core";

// Raw bytes (the pipeline's draft .docx, ~50 KB). Kept in the row rather than a
// storage bucket so a draft and its verification record live together.
const bytea = customType<{ data: Buffer; driverData: Buffer }>({
  dataType: () => "bytea",
});

// ----------------------------- ENUMS ---------------------------------

export const careerStage = pgEnum("career_stage", [
  "medical_student", "dental_student", "nursing_student", "masters_student",
  "phd_student", "other_student",
  "foundation_doctor", "junior_doctor", "registrar", "consultant",
  "dentist", "qualified_nurse", "physician_associate",
  "advanced_clinical_practitioner", "physiotherapist", "pharmacist",
  "professor", "postdoc", "staff_grade", "other",
]);

export const experienceLevel = pgEnum("experience_level", [
  "beginner_welcome", "some_experience", "experienced_only",
]);

export const projectType = pgEnum("project_type", [
  "audit", "systematic_review", "literature_review", "case_study",
  "retrospective", "prospective_study", "poster", "teaching", "other",
]);

export const projectStatus = pgEnum("project_status", [
  "draft", "open", "in_progress", "closed", "completed",
]);

export const applicationStatus = pgEnum("application_status", [
  "pending", "shortlisted", "accepted", "rejected", "withdrawn",
]);

export const verificationType = pgEnum("verification_type", [
  "university_email", "nhs_email", "linkedin", "manual", "login_email",
]);

export const verificationStatus = pgEnum("verification_status", [
  "pending", "verified", "rejected",
]);

export const conversationType = pgEnum("conversation_type", [
  "application_dm", "project_chat",
]);

export const reviewDirection = pgEnum("review_direction", [
  "supervisor_to_member", "member_to_supervisor",
]);

export const notificationType = pgEnum("notification_type", [
  "application", "message", "review", "match", "system",
]);

// --------------------------- PROFILES --------------------------------

export const profiles = pgTable("profiles", {
  id: uuid("id").primaryKey(), // == auth.users.id
  fullName: text("full_name").notNull(),
  email: text("email").notNull().unique(),
  avatarUrl: text("avatar_url"),
  summary: text("summary"),
  university: text("university"),
  careerStage: careerStage("career_stage").notNull().default("other"),
  careerStageOther: text("career_stage_other"),
  linkedinUrl: text("linkedin_url"),
  // Private contact detail, optional. Never rendered on a public profile —
  // only revealed to the counterparty once an application is accepted. The
  // account `email` is the always-present contact method; phone is extra.
  contactPhone: text("contact_phone"),
  specialty: text("specialty"),
  isVerified: boolean("is_verified").notNull().default(false),
  emailConfirmedAt: timestamp("email_confirmed_at", { withTimezone: true }),
  canSupervise: boolean("can_supervise").notNull().default(false),
  isNewResearcher: boolean("is_new_researcher").notNull().default(true),
  reliabilityScore: numeric("reliability_score", { precision: 3, scale: 2 }),
  availability: text("availability"),
  availabilityHoursPerWeek: integer("availability_hours_per_week"),
  preferredProjectTypes: text("preferred_project_types"),
  preferredSpecialties: text("preferred_specialties"),
  profileCompleteness: integer("profile_completeness").notNull().default(0),
  // Amendment §9: the channel the user first arrived through, captured on
  // first visit (cookie) and written here once at signup. First touch wins;
  // an unknown/missing code is recorded as "direct".
  refCode: text("ref_code"),
  // Amendment §8.5: opt-out for the "publish your listing" nudge emails only,
  // kept separate from transactional email.
  listingNudgeOptOut: boolean("listing_nudge_opt_out").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

export const skills = pgTable("skills", {
  id: serial("id").primaryKey(),
  name: text("name").notNull().unique(),
});

export const profileSkills = pgTable("profile_skills", {
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  skillId: integer("skill_id").notNull().references(() => skills.id, { onDelete: "cascade" }),
}, (t) => [primaryKey({ columns: [t.profileId, t.skillId] })]);

export const profileCertifications = pgTable("profile_certifications", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  proofUrl: text("proof_url"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("profile_certifications_profile_idx").on(t.profileId)]);

export const publications = pgTable("publications", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  url: text("url"),
  year: integer("year"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const verifications = pgTable("verifications", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  type: verificationType("type").notNull(),
  status: verificationStatus("status").notNull().default("pending"),
  detail: text("detail"),
  token: text("token"),
  expiresAt: timestamp("expires_at", { withTimezone: true }),
  verifiedAt: timestamp("verified_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("verifications_token_idx").on(t.token)]);

// --------------------------- PROJECTS --------------------------------

export const projects = pgTable("projects", {
  id: uuid("id").primaryKey().defaultRandom(),
  ownerId: uuid("owner_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  supervisorId: uuid("supervisor_id").references(() => profiles.id),
  title: text("title").notNull(),
  description: text("description").notNull(),
  projectType: projectType("project_type").notNull(),
  experienceLevel: experienceLevel("experience_level").notNull(),
  specialty: text("specialty"),
  roleCategory: text("role_category"),
  isBeginnerFriendly: boolean("is_beginner_friendly").notNull().default(false),
  positionsAvailable: integer("positions_available").notNull().default(1),
  status: projectStatus("status").notNull().default("open"),
  applicationDeadline: date("application_deadline"),
  // Amendment §8.4: a project auto-drafted from a delivered guide links back to
  // its order. Guide-sourced listings get priority placement (§8.7) and mark
  // the owner as a "guide lister" for the credit tier (§8.9). Set null keeps
  // the listing if the order row is ever removed.
  sourceGuideOrderId: uuid("source_guide_order_id")
    .references(() => guideOrders.id, { onDelete: "set null" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("projects_status_idx").on(t.status),
  index("projects_experience_idx").on(t.experienceLevel),
  index("projects_specialty_idx").on(t.specialty),
  index("projects_source_guide_idx").on(t.sourceGuideOrderId),
]);

// ------------------------- APPLICATIONS ------------------------------

export const applications = pgTable("applications", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  applicantId: uuid("applicant_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  status: applicationStatus("status").notNull().default("pending"),
  motivation: text("motivation").notNull(),
  suitability: text("suitability").notNull(),
  hoursPerWeek: integer("hours_per_week"),
  skillsSummary: text("skills_summary"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  unique("applications_project_applicant_key").on(t.projectId, t.applicantId),
  // index supports the rolling 3-per-7-days rate limit lookup
  index("applications_applicant_time_idx").on(t.applicantId, t.createdAt),
  index("applications_project_idx").on(t.projectId),
]);

// --------------------- PUBLIC Q&A ON LISTINGS ------------------------

export const listingQuestions = pgTable("listing_questions", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  askerId: uuid("asker_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  question: text("question").notNull(),
  answer: text("answer"),
  answeredAt: timestamp("answered_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// ---------------------- PRIVATE MESSAGING ----------------------------

export const conversations = pgTable("conversations", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").references(() => projects.id, { onDelete: "cascade" }),
  type: conversationType("type").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const conversationParticipants = pgTable("conversation_participants", {
  conversationId: uuid("conversation_id").notNull().references(() => conversations.id, { onDelete: "cascade" }),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
}, (t) => [primaryKey({ columns: [t.conversationId, t.profileId] })]);

export const messages = pgTable("messages", {
  id: uuid("id").primaryKey().defaultRandom(),
  conversationId: uuid("conversation_id").notNull().references(() => conversations.id, { onDelete: "cascade" }),
  senderId: uuid("sender_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  body: text("body").notNull(),
  readAt: timestamp("read_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("messages_conversation_idx").on(t.conversationId, t.createdAt)]);

// ----------------------- REVIEWS / REPUTATION ------------------------

export const reviews = pgTable("reviews", {
  id: uuid("id").primaryKey().defaultRandom(),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  reviewerId: uuid("reviewer_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  revieweeId: uuid("reviewee_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  direction: reviewDirection("direction").notNull(),
  ratingOverall: numeric("rating_overall", { precision: 2, scale: 1 }).notNull(),
  reliability: integer("reliability"),
  communication: integer("communication"),
  contribution: integer("contribution"),
  meetsDeadlines: integer("meets_deadlines"),
  supervision: integer("supervision"),
  teaching: integer("teaching"),
  fairAuthorship: integer("fair_authorship"),
  comment: text("comment"),
  isAnonymous: boolean("is_anonymous").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  unique("reviews_project_reviewer_reviewee_key").on(t.projectId, t.reviewerId, t.revieweeId),
  index("reviews_reviewee_idx").on(t.revieweeId),
]);

// --------------------------- BADGES ----------------------------------

export const badges = pgTable("badges", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  name: text("name").notNull(),
  description: text("description"),
});

export const userBadges = pgTable("user_badges", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  badgeId: integer("badge_id").notNull().references(() => badges.id, { onDelete: "cascade" }),
  awardedAt: timestamp("awarded_at", { withTimezone: true }).notNull().defaultNow(),
  expiresAt: timestamp("expires_at", { withTimezone: true }),
}, (t) => [unique("user_badges_profile_badge_key").on(t.profileId, t.badgeId)]);

// ------------------------ NOTIFICATIONS ------------------------------

export const notifications = pgTable("notifications", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  type: notificationType("type").notNull(),
  title: text("title").notNull(),
  body: text("body"),
  link: text("link"),
  readAt: timestamp("read_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("notifications_unread_idx").on(t.profileId, t.readAt)]);

// --------------------- SAVED / BOOKMARKED ----------------------------

export const savedProjects = pgTable("saved_projects", {
  profileId: uuid("profile_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  projectId: uuid("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [primaryKey({ columns: [t.profileId, t.projectId] })]);

// ------------------------ ERROR MONITORING ---------------------------

// Unhandled server errors captured by instrumentation.onRequestError, shown
// on /admin. Rows older than 30 days are pruned on insert.
export const appErrors = pgTable("app_errors", {
  id: uuid("id").primaryKey().defaultRandom(),
  message: text("message").notNull(),
  digest: text("digest"),
  stack: text("stack"),
  path: text("path"),
  method: text("method"),
  routePath: text("route_path"),
  routeType: text("route_type"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("app_errors_created_idx").on(t.createdAt)]);

// ------------------------ TRUST & SAFETY -----------------------------

export const reportTargetType = pgEnum("report_target_type", [
  "project", "question", "profile", "review", "availability_listing",
]);

export const reportStatus = pgEnum("report_status", [
  "open", "actioned", "dismissed",
]);

// User reports about content or conduct (abuse, data protection, spam...).
// Reviewed on /admin, which can also unpublish/remove the target.
export const reports = pgTable("reports", {
  id: uuid("id").primaryKey().defaultRandom(),
  reporterId: uuid("reporter_id").notNull().references(() => profiles.id, { onDelete: "cascade" }),
  targetType: reportTargetType("target_type").notNull(),
  targetId: uuid("target_id").notNull(),
  reason: text("reason").notNull(),
  status: reportStatus("status").notNull().default("open"),
  resolvedAt: timestamp("resolved_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("reports_status_idx").on(t.status, t.createdAt)]);

// ------------------------ PUBLICATION GUIDES -------------------------

// Paid, bespoke, human-verified guides (docs spec §3). The proforma is
// completed BEFORE payment; an order starts as 'submitted' and only becomes
// 'paid' on the Stripe webhook (never on the browser redirect).
export const guideOrderStatus = pgEnum("guide_order_status", [
  "submitted", "paid", "in_progress", "delivered", "refunded",
]);

export const guideOrders = pgTable("guide_orders", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull()
    .references(() => profiles.id, { onDelete: "cascade" }),
  // Full proforma answers as JSON; fields needed for queries are first-class.
  proforma: text("proforma").notNull(),
  fullName: text("full_name").notNull(),
  email: text("email").notNull(),
  status: guideOrderStatus("status").notNull().default("submitted"),
  // Pricing resolved server-side at checkout-session creation. Reservation
  // (discount_applied + checkout_started_at) is claimed under a row lock on
  // guide_pricing_config; the public counter counts paid orders only.
  discountApplied: boolean("discount_applied").notNull().default(false),
  priceAtCheckoutPence: integer("price_at_checkout_pence"),
  pricePaidPence: integer("price_paid_pence"),
  checkoutStartedAt: timestamp("checkout_started_at", { withTimezone: true }),
  stripeSessionId: text("stripe_session_id"),
  stripePaymentIntentId: text("stripe_payment_intent_id"),
  // UK consumer-law consents (spec §3.2): both recorded with timestamp + IP.
  consentImmediateAt: timestamp("consent_immediate_at", { withTimezone: true }),
  consentTermsAt: timestamp("consent_terms_at", { withTimezone: true }),
  consentIp: text("consent_ip"),
  // Location evidence, retained ≥10 years (spec §7.6). Country is queryable.
  ipCountry: text("ip_country"),
  billingCountry: text("billing_country"),
  cardCountry: text("card_country"),
  countryMismatch: boolean("country_mismatch").notNull().default(false),
  // The load-bearing human step (spec §7.5): who verified the guide, when,
  // and what they changed or checked.
  verifiedBy: text("verified_by"),
  verifiedAt: timestamp("verified_at", { withTimezone: true }),
  verificationNote: text("verification_note"),
  paidAt: timestamp("paid_at", { withTimezone: true }),
  deliveredAt: timestamp("delivered_at", { withTimezone: true }),
  overdueAlertedAt: timestamp("overdue_alerted_at", { withTimezone: true }),
  // Amendment §8.5: the two "publish your listing" nudges (10 and 30 calendar
  // days after delivery). Never more than two, and only while no listing has
  // been published from this guide.
  listingNudge10At: timestamp("listing_nudge_10_at", { withTimezone: true }),
  listingNudge30At: timestamp("listing_nudge_30_at", { withTimezone: true }),
  reviewToken: text("review_token").unique(),
  reviewRequestedAt: timestamp("review_requested_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("guide_orders_profile_idx").on(t.profileId),
  index("guide_orders_status_idx").on(t.status, t.createdAt),
  index("guide_orders_session_idx").on(t.stripeSessionId),
]);

// Delivered files (PDF + editable DOCX + XLSX template) in a private bucket,
// downloaded only through an authenticated route — the account is the licence.
export const guideOrderFiles = pgTable("guide_order_files", {
  id: uuid("id").primaryKey().defaultRandom(),
  orderId: uuid("order_id").notNull()
    .references(() => guideOrders.id, { onDelete: "cascade" }),
  path: text("path").notNull(),
  filename: text("filename").notNull(),
  contentType: text("content_type").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("guide_order_files_order_idx").on(t.orderId)]);

// Single-row config (id = 1), administrator-editable without a deploy.
// Prices are pence and are the TOTAL payable — nothing is added at checkout
// (DMCC drip-pricing ban, spec §7.3).
// Amendment §2 — a three-band price ladder, all quantities and prices
// administrator-configurable (nothing hardcoded):
//   1. the first `free_quantity` guides are free (£0);
//   2. the next `intro_quantity` guides are `intro_price_pence` (the £25 tier);
//   3. thereafter, `standard_price_pence` (£45).
// `payments_enabled` is the launch toggle: while OFF, the checkout step is
// skipped and every request goes straight to the queue at no charge, even
// though the full Stripe path is built.
export const guidePricingConfig = pgTable("guide_pricing_config", {
  id: integer("id").primaryKey().default(1),
  standardPricePence: integer("standard_price_pence").notNull().default(4500),
  introPricePence: integer("intro_price_pence").notNull().default(2500),
  introQuantity: integer("intro_quantity").notNull().default(25),
  freeQuantity: integer("free_quantity").notNull().default(25),
  paymentsEnabled: boolean("payments_enabled").notNull().default(false),
  // Countries blocked at checkout (ISO 3166-1 alpha-2), admin-editable.
  blockedCountries: text("blocked_countries").array().notNull(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Reviews (spec §3.5): admin-moderated, never edited, complimentary guides
// disclosed via a badge that cannot be hidden.
export const guideReviewStatus = pgEnum("guide_review_status", [
  "pending", "approved", "rejected", "removed",
]);

export const guideReviews = pgTable("guide_reviews", {
  id: uuid("id").primaryKey().defaultRandom(),
  // Nullable for admin-created reviews from colleagues outside the payment
  // flow — those must have complimentary_guide = true.
  orderId: uuid("order_id").references(() => guideOrders.id, { onDelete: "set null" }),
  reviewerName: text("reviewer_name").notNull(),
  reviewerRole: text("reviewer_role").notNull(),
  reviewerInstitution: text("reviewer_institution"),
  rating: integer("rating").notNull(),
  body: text("body").notNull(),
  guideTopic: text("guide_topic"),
  complimentaryGuide: boolean("complimentary_guide").notNull().default(false),
  status: guideReviewStatus("status").notNull().default("pending"),
  publishedAt: timestamp("published_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("guide_reviews_status_idx").on(t.status, t.publishedAt)]);

// ------------------- GUIDE PIPELINE (build spec §5) -------------------
// Written by the Python guide pipeline (service role) and read by the admin
// verification screen (Stage 6). One run per pipeline attempt for an order; a
// rejected run leads to a fresh run with the rejected title passed back as
// negative context. No include/exclude boolean exists anywhere here: papers
// carry a visible graded status with its reason and evidence basis.

export const guideRunStatus = pgEnum("guide_run_status", [
  "running", "found", "needs_contact", "failed",
]);

export const guideRuns = pgTable("guide_runs", {
  id: uuid("id").primaryKey().defaultRandom(),
  orderId: uuid("order_id").references(() => guideOrders.id, { onDelete: "cascade" }),
  status: guideRunStatus("status").notNull().default("running"),
  title: text("title"),
  publicationType: text("publication_type"),
  axis: text("axis"),
  contactReason: text("contact_reason"), // why the user must be emailed (needs_contact)
  costUsd: numeric("cost_usd", { precision: 10, scale: 4 }),
  pipelineVersion: text("pipeline_version"),
  results: jsonb("results"), // the full results record (criteria, selection, guide parts)
  metrics: jsonb("metrics"), // the per-guide feedback record
  guideDocx: bytea("guide_docx"), // the draft guide, for the reviewer
  startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
  finishedAt: timestamp("finished_at", { withTimezone: true }),
}, (t) => [index("guide_runs_order_idx").on(t.orderId, t.startedAt)]);

// Every candidate a run generated, with its gate results and score.
export const guideRunCandidates = pgTable("guide_run_candidates", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  normalizedTitle: text("normalized_title").notNull(),
  axis: text("axis").notNull(),
  batch: integer("batch").notNull(),
  outcome: text("outcome").notNull(), // pass | flag | downgrade | reject
  gates: jsonb("gates").notNull(), // every gate with outcome, value and threshold
  score: jsonb("score"), // Stage 4b components and total, when scored
  eligibleStudies: integer("eligible_studies"),
  recentReviews: integer("recent_reviews"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("guide_run_candidates_run_idx").on(t.runId),
  index("guide_run_candidates_title_idx").on(t.normalizedTitle),
]);

// Spec §5's highest-value item: a question offered to one customer is never
// offered to another. One row per normalised title that reached a reviewer.
export const guideTitleRegistry = pgTable("guide_title_registry", {
  normalizedTitle: text("normalized_title").primaryKey(),
  title: text("title").notNull(),
  firstRunId: uuid("first_run_id").references(() => guideRuns.id, { onDelete: "set null" }),
  orderId: uuid("order_id").references(() => guideOrders.id, { onDelete: "set null" }),
  status: text("status").notNull().default("offered"), // offered | approved | rejected
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// Every search run: source, exact query, result count, time (spec §4 Stage 5).
export const guideSearches = pgTable("guide_searches", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  source: text("source").notNull(),
  query: text("query").notNull(),
  resultCount: integer("result_count"),
  runAt: timestamp("run_at", { withTimezone: true }).notNull(),
}, (t) => [index("guide_searches_run_idx").on(t.runId)]);

// The chosen question's papers with their graded screening estimate.
export const guideScreenedPapers = pgTable("guide_screened_papers", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  identifier: text("identifier").notNull(), // PMID, or Europe PMC id for preprints
  idType: text("id_type").notNull().default("PMID"),
  doi: text("doi"),
  title: text("title").notNull(),
  year: integer("year"),
  journal: text("journal"),
  status: text("status").notNull(), // likely eligible | likely ineligible | unclear, check full text
  reason: text("reason").notNull(),
  evidenceBasis: text("evidence_basis").notNull(), // abstract only | full text (...)
  attributes: jsonb("attributes"),
}, (t) => [index("guide_screened_papers_run_idx").on(t.runId, t.status)]);

// The record kept for every PROSPERO check (spec §3.5): retain permanently.
export const guideProsperoChecks = pgTable("guide_prospero_checks", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  searchTerms: text("search_terms").notNull(),
  checkedOn: date("checked_on").notNull(),
  mirrorCoveredTo: date("mirror_covered_to").notNull(),
  mirrorRefreshedAt: timestamp("mirror_refreshed_at", { withTimezone: true }),
  verdict: text("verdict").notNull(), // registered | review | clear
  matches: jsonb("matches").notNull(),
}, (t) => [index("guide_prospero_checks_run_idx").on(t.runId)]);

// Stage 5b: the model's choice between tied questions, its rationale per
// criterion, and the reviewer's override (overrides are counted to tune it).
export const guideTieBreaks = pgTable("guide_tie_breaks", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  candidates: jsonb("candidates").notNull(),
  modelChoice: integer("model_choice").notNull(),
  rationale: jsonb("rationale").notNull(),
  summary: text("summary"),
  overrideChoice: integer("override_choice"),
  overrideReason: text("override_reason"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("guide_tie_breaks_run_idx").on(t.runId)]);

// Stage 6: who verified, when, what changed, the outcome, and the date of the
// reviewer's live PROSPERO check on the title that ships.
export const guideVerificationAction = pgEnum("guide_verification_action", [
  "approved", "edited_and_approved", "rejected",
]);

export const guideVerifications = pgTable("guide_verifications", {
  id: uuid("id").primaryKey().defaultRandom(),
  runId: uuid("run_id").notNull().references(() => guideRuns.id, { onDelete: "cascade" }),
  orderId: uuid("order_id").references(() => guideOrders.id, { onDelete: "set null" }),
  reviewer: text("reviewer").notNull(),
  action: guideVerificationAction("action").notNull(),
  editedTitle: text("edited_title"),
  notes: text("notes"),
  liveProsperoCheckedOn: date("live_prospero_checked_on"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("guide_verifications_run_idx").on(t.runId)]);

// ------------------------ TEACHING PLATFORM --------------------------

// Commissioned topics shown on /teach — administrator-editable rows, never
// hardcoded (docs spec §4.1.3). Seeded by drizzle/manual/0005_teaching_seed.sql.
export const teachingTopicStatus = pgEnum("teaching_topic_status", [
  "accepting_submissions", "under_review", "filled",
]);

export const teachingTopics = pgTable("teaching_topics", {
  id: serial("id").primaryKey(),
  title: text("title").notNull(),
  description: text("description").notNull(),
  format: text("format").notNull(),
  deadline: date("deadline"),
  status: teachingTopicStatus("status").notNull().default("accepting_submissions"),
  sortOrder: integer("sort_order").notNull().default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// Rolling review, explicitly not a competition (spec §4.2). A submission
// cannot reach "scheduled"/published until the named clinician has confirmed
// via their emailed token link — applicant-forwarded confirmations are
// trivially forged, so the platform contacts the clinician directly.
export const teachingSubmissionStatus = pgEnum("teaching_submission_status", [
  "submitted", "under_review", "revisions_requested", "approved",
  "clinician_verification", "scheduled", "delivered", "declined",
]);

export const clinicianVerificationStatus = pgEnum("clinician_verification_status", [
  "pending", "confirmed", "declined",
]);

export const teachingDeliveryFormat = pgEnum("teaching_delivery_format", [
  "live_with_recordings", "live_only", "recorded_only",
]);

export const teachingSubmissions = pgTable("teaching_submissions", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull()
    .references(() => profiles.id, { onDelete: "cascade" }),
  // null topic = "Proposing my own topic"
  topicId: integer("topic_id").references(() => teachingTopics.id, { onDelete: "set null" }),
  applicantGmcNumber: text("applicant_gmc_number"),
  title: text("title").notNull(),
  description: text("description").notNull(),
  learningObjectives: text("learning_objectives").array().notNull(), // 3 to 5
  targetAudience: text("target_audience").array().notNull(),
  sessionsPlan: text("sessions_plan").notNull(), // number of sessions + duration
  deliveryFormat: teachingDeliveryFormat("delivery_format").notNull(),
  startAvailability: text("start_availability").notNull(),
  relevantExperience: text("relevant_experience").notNull(),
  // Path inside the private teaching-materials bucket; served only via
  // service-role signed URLs, never a public URL (spec §2.2).
  materialsPath: text("materials_path").notNull(),
  materialsFilename: text("materials_filename").notNull(),
  status: teachingSubmissionStatus("status").notNull().default("submitted"),
  adminFeedback: text("admin_feedback"),
  clinicianName: text("clinician_name").notNull(),
  clinicianGrade: text("clinician_grade").notNull(),
  clinicianSpecialty: text("clinician_specialty").notNull(),
  clinicianInstitution: text("clinician_institution").notNull(),
  clinicianGmcNumber: text("clinician_gmc_number").notNull(),
  clinicianEmail: text("clinician_email").notNull(),
  clinicianToken: text("clinician_token").notNull().unique(),
  clinicianStatus: clinicianVerificationStatus("clinician_status").notNull().default("pending"),
  clinicianRespondedAt: timestamp("clinician_responded_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("teaching_submissions_profile_idx").on(t.profileId),
  index("teaching_submissions_status_idx").on(t.status, t.createdAt),
]);

// Version history: the pre-edit payload is snapshotted on every resubmission
// against the same record (spec §4.2 review process).
export const teachingSubmissionRevisions = pgTable("teaching_submission_revisions", {
  id: uuid("id").primaryKey().defaultRandom(),
  submissionId: uuid("submission_id").notNull()
    .references(() => teachingSubmissions.id, { onDelete: "cascade" }),
  payload: text("payload").notNull(), // JSON snapshot of the replaced version
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("teaching_submission_revisions_submission_idx").on(t.submissionId)]);

// -------------- AVAILABLE FOR PROJECTS (reverse board) ---------------

// A user advertising themselves to project listers. One listing per user
// (unique profile_id; editing replaces). Listings auto-expire after 60 days:
// expiry is enforced at query time (status = 'active' AND expires_at > now())
// so no cron is required for correctness; the renewal email is best-effort.
// Expired/removed listings are retained so users can reactivate, and
// "found_project" records the outcome metric that tells us the board works.
export const availabilityListingStatus = pgEnum("availability_listing_status", [
  "active", "found_project", "removed",
]);

export const availabilityListings = pgTable("availability_listings", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull().unique()
    .references(() => profiles.id, { onDelete: "cascade" }),
  headline: text("headline").notNull(),
  // Privacy: the card can show initials instead of the full name, and the
  // institution can be withheld. Email addresses are never rendered.
  displayInitialsOnly: boolean("display_initials_only").notNull().default(false),
  showInstitution: boolean("show_institution").notNull().default(true),
  region: text("region"),
  specialties: text("specialties"), // comma-separated, max 3
  skills: text("skills").array().notNull(), // values from SKILLS_OFFERED
  hoursPerWeek: integer("hours_per_week"),
  availableFrom: date("available_from"),
  previousPublications: text("previous_publications"),
  lookingFor: text("looking_for").notNull(),
  status: availabilityListingStatus("status").notNull().default("active"),
  expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  renewalEmailedAt: timestamp("renewal_emailed_at", { withTimezone: true }),
  foundProjectAt: timestamp("found_project_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("availability_listings_board_idx").on(t.status, t.expiresAt, t.updatedAt),
]);

// Relay messages sent to a listing owner ("Get in touch"). Both sides are
// logged for abuse investigation; the owner's email is never exposed.
export const listingContacts = pgTable("listing_contacts", {
  id: uuid("id").primaryKey().defaultRandom(),
  listingId: uuid("listing_id").notNull()
    .references(() => availabilityListings.id, { onDelete: "cascade" }),
  senderId: uuid("sender_id").notNull()
    .references(() => profiles.id, { onDelete: "cascade" }),
  recipientId: uuid("recipient_id").notNull()
    .references(() => profiles.id, { onDelete: "cascade" }),
  body: text("body").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  // Supports the 10-per-sender-per-day rate limit lookup.
  index("listing_contacts_sender_time_idx").on(t.senderId, t.createdAt),
  index("listing_contacts_listing_idx").on(t.listingId),
]);

// Contact-form submissions (feedback, complaints, data protection requests).
// senderId is null for logged-out visitors.
export const contactMessages = pgTable("contact_messages", {
  id: uuid("id").primaryKey().defaultRandom(),
  senderId: uuid("sender_id").references(() => profiles.id, { onDelete: "set null" }),
  email: text("email"),
  topic: text("topic").notNull(),
  message: text("message").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// --------------- PLATFORM CONFIG (member benefits, §8) ----------------

// Single-row config (id = 1), administrator-editable without a deploy. Holds
// the tunables the amendment insists stay configurable: the application credit
// tiers (§8.9), the bounded direct-support allowance (§8.8) and the optional
// 14-day vesting flag for benefits (§8.7, off initially).
export const platformConfig = pgTable("platform_config", {
  id: integer("id").primaryKey().default(1),
  // §8.9 weekly application credits by member type.
  creditsStandard: integer("credits_standard").notNull().default(3),
  creditsLister: integer("credits_lister").notNull().default(6),
  creditsGuideLister: integer("credits_guide_lister").notNull().default(9),
  // §8.8 bounded direct support.
  supportAllowance: integer("support_allowance").notNull().default(3),
  supportResponseDays: integer("support_response_days").notNull().default(7),
  // §8.7 optional anti-gaming: benefits vest only after a listing has been live
  // this many days. 0 = off (the launch default).
  vestListingDays: integer("vest_listing_days").notNull().default(0),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Bounded direct-support questions (§8.8). One row per question; the allowance
// is enforced in app logic by counting a user's rows against platform_config.
export const supportQuestions = pgTable("support_questions", {
  id: uuid("id").primaryKey().defaultRandom(),
  profileId: uuid("profile_id").notNull()
    .references(() => profiles.id, { onDelete: "cascade" }),
  orderId: uuid("order_id").references(() => guideOrders.id, { onDelete: "set null" }),
  question: text("question").notNull(),
  answer: text("answer"),
  answeredAt: timestamp("answered_at", { withTimezone: true }),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("support_questions_profile_idx").on(t.profileId, t.createdAt)]);

// ------------------- CHANNEL ATTRIBUTION (§9) ------------------------

// Administrator-managed referral codes (§9.3). One distinct code per
// influencer/society/institution. Codes are lowercase alphanumeric with
// hyphens and carry no personal data. Unknown codes seen in the wild are still
// recorded (as-is) so a mistyped or retired code is never lost.
export const referralCodes = pgTable("referral_codes", {
  id: serial("id").primaryKey(),
  code: text("code").notNull().unique(),
  label: text("label").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

// First-touch visit log (§9.2), so the top of the funnel (visits) can be
// reported per code. One row per new visitor (deduped client-side), inserted
// server-side from the captured ref cookie.
export const attributionVisits = pgTable("attribution_visits", {
  id: uuid("id").primaryKey().defaultRandom(),
  code: text("code").notNull(), // "direct" when no code was present
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [index("attribution_visits_code_idx").on(t.code, t.createdAt)]);
