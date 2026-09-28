CREATE TYPE "public"."guide_run_status" AS ENUM('running', 'found', 'needs_contact', 'failed');--> statement-breakpoint
CREATE TYPE "public"."guide_verification_action" AS ENUM('approved', 'edited_and_approved', 'rejected');--> statement-breakpoint
CREATE TABLE "guide_prospero_checks" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"title" text NOT NULL,
	"search_terms" text NOT NULL,
	"checked_on" date NOT NULL,
	"mirror_covered_to" date NOT NULL,
	"mirror_refreshed_at" timestamp with time zone,
	"verdict" text NOT NULL,
	"matches" jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_run_candidates" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"title" text NOT NULL,
	"normalized_title" text NOT NULL,
	"axis" text NOT NULL,
	"batch" integer NOT NULL,
	"outcome" text NOT NULL,
	"gates" jsonb NOT NULL,
	"score" jsonb,
	"eligible_studies" integer,
	"recent_reviews" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid,
	"status" "guide_run_status" DEFAULT 'running' NOT NULL,
	"title" text,
	"publication_type" text,
	"axis" text,
	"contact_reason" text,
	"cost_usd" numeric(10, 4),
	"pipeline_version" text,
	"results" jsonb,
	"metrics" jsonb,
	"guide_docx" "bytea",
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "guide_screened_papers" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"identifier" text NOT NULL,
	"id_type" text DEFAULT 'PMID' NOT NULL,
	"doi" text,
	"title" text NOT NULL,
	"year" integer,
	"journal" text,
	"status" text NOT NULL,
	"reason" text NOT NULL,
	"evidence_basis" text NOT NULL,
	"attributes" jsonb
);
--> statement-breakpoint
CREATE TABLE "guide_searches" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"source" text NOT NULL,
	"query" text NOT NULL,
	"result_count" integer,
	"run_at" timestamp with time zone NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_tie_breaks" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"candidates" jsonb NOT NULL,
	"model_choice" integer NOT NULL,
	"rationale" jsonb NOT NULL,
	"summary" text,
	"override_choice" integer,
	"override_reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_title_registry" (
	"normalized_title" text PRIMARY KEY NOT NULL,
	"title" text NOT NULL,
	"first_run_id" uuid,
	"order_id" uuid,
	"status" text DEFAULT 'offered' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_verifications" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"run_id" uuid NOT NULL,
	"order_id" uuid,
	"reviewer" text NOT NULL,
	"action" "guide_verification_action" NOT NULL,
	"edited_title" text,
	"notes" text,
	"live_prospero_checked_on" date,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "guide_prospero_checks" ADD CONSTRAINT "guide_prospero_checks_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_run_candidates" ADD CONSTRAINT "guide_run_candidates_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_runs" ADD CONSTRAINT "guide_runs_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_screened_papers" ADD CONSTRAINT "guide_screened_papers_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_searches" ADD CONSTRAINT "guide_searches_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_tie_breaks" ADD CONSTRAINT "guide_tie_breaks_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_title_registry" ADD CONSTRAINT "guide_title_registry_first_run_id_guide_runs_id_fk" FOREIGN KEY ("first_run_id") REFERENCES "public"."guide_runs"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_title_registry" ADD CONSTRAINT "guide_title_registry_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_verifications" ADD CONSTRAINT "guide_verifications_run_id_guide_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."guide_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_verifications" ADD CONSTRAINT "guide_verifications_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "guide_prospero_checks_run_idx" ON "guide_prospero_checks" USING btree ("run_id");--> statement-breakpoint
CREATE INDEX "guide_run_candidates_run_idx" ON "guide_run_candidates" USING btree ("run_id");--> statement-breakpoint
CREATE INDEX "guide_run_candidates_title_idx" ON "guide_run_candidates" USING btree ("normalized_title");--> statement-breakpoint
CREATE INDEX "guide_runs_order_idx" ON "guide_runs" USING btree ("order_id","started_at");--> statement-breakpoint
CREATE INDEX "guide_screened_papers_run_idx" ON "guide_screened_papers" USING btree ("run_id","status");--> statement-breakpoint
CREATE INDEX "guide_searches_run_idx" ON "guide_searches" USING btree ("run_id");--> statement-breakpoint
CREATE INDEX "guide_tie_breaks_run_idx" ON "guide_tie_breaks" USING btree ("run_id");--> statement-breakpoint
CREATE INDEX "guide_verifications_run_idx" ON "guide_verifications" USING btree ("run_id");