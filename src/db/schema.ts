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
