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
} from "drizzle-orm/pg-core";

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
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
}, (t) => [
  index("projects_status_idx").on(t.status),
  index("projects_experience_idx").on(t.experienceLevel),
  index("projects_specialty_idx").on(t.specialty),
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
  learningObjectives: text("learning_objectives").array().notNull(), // 3–5
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
