CREATE TYPE "public"."clinician_verification_status" AS ENUM('pending', 'confirmed', 'declined');--> statement-breakpoint
CREATE TYPE "public"."teaching_delivery_format" AS ENUM('live_with_recordings', 'live_only', 'recorded_only');--> statement-breakpoint
CREATE TYPE "public"."teaching_submission_status" AS ENUM('submitted', 'under_review', 'revisions_requested', 'approved', 'clinician_verification', 'scheduled', 'delivered', 'declined');--> statement-breakpoint
CREATE TYPE "public"."teaching_topic_status" AS ENUM('accepting_submissions', 'under_review', 'filled');--> statement-breakpoint
CREATE TABLE "teaching_submission_revisions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"submission_id" uuid NOT NULL,
	"payload" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "teaching_submissions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"profile_id" uuid NOT NULL,
	"topic_id" integer,
	"applicant_gmc_number" text,
	"title" text NOT NULL,
	"description" text NOT NULL,
	"learning_objectives" text[] NOT NULL,
	"target_audience" text[] NOT NULL,
	"sessions_plan" text NOT NULL,
	"delivery_format" "teaching_delivery_format" NOT NULL,
	"start_availability" text NOT NULL,
	"relevant_experience" text NOT NULL,
	"materials_path" text NOT NULL,
	"materials_filename" text NOT NULL,
	"status" "teaching_submission_status" DEFAULT 'submitted' NOT NULL,
	"admin_feedback" text,
	"clinician_name" text NOT NULL,
	"clinician_grade" text NOT NULL,
	"clinician_specialty" text NOT NULL,
	"clinician_institution" text NOT NULL,
	"clinician_gmc_number" text NOT NULL,
	"clinician_email" text NOT NULL,
	"clinician_token" text NOT NULL,
	"clinician_status" "clinician_verification_status" DEFAULT 'pending' NOT NULL,
	"clinician_responded_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "teaching_submissions_clinician_token_unique" UNIQUE("clinician_token")
);
--> statement-breakpoint
CREATE TABLE "teaching_topics" (
	"id" serial PRIMARY KEY NOT NULL,
	"title" text NOT NULL,
	"description" text NOT NULL,
	"format" text NOT NULL,
	"deadline" date,
	"status" "teaching_topic_status" DEFAULT 'accepting_submissions' NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "teaching_submission_revisions" ADD CONSTRAINT "teaching_submission_revisions_submission_id_teaching_submissions_id_fk" FOREIGN KEY ("submission_id") REFERENCES "public"."teaching_submissions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "teaching_submissions" ADD CONSTRAINT "teaching_submissions_profile_id_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "teaching_submissions" ADD CONSTRAINT "teaching_submissions_topic_id_teaching_topics_id_fk" FOREIGN KEY ("topic_id") REFERENCES "public"."teaching_topics"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "teaching_submission_revisions_submission_idx" ON "teaching_submission_revisions" USING btree ("submission_id");--> statement-breakpoint
CREATE INDEX "teaching_submissions_profile_idx" ON "teaching_submissions" USING btree ("profile_id");--> statement-breakpoint
CREATE INDEX "teaching_submissions_status_idx" ON "teaching_submissions" USING btree ("status","created_at");