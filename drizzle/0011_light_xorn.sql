CREATE TABLE "attribution_visits" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"code" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "platform_config" (
	"id" integer PRIMARY KEY DEFAULT 1 NOT NULL,
	"credits_standard" integer DEFAULT 3 NOT NULL,
	"credits_lister" integer DEFAULT 6 NOT NULL,
	"credits_guide_lister" integer DEFAULT 9 NOT NULL,
	"support_allowance" integer DEFAULT 3 NOT NULL,
	"support_response_days" integer DEFAULT 7 NOT NULL,
	"vest_listing_days" integer DEFAULT 0 NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "referral_codes" (
	"id" serial PRIMARY KEY NOT NULL,
	"code" text NOT NULL,
	"label" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "referral_codes_code_unique" UNIQUE("code")
);
--> statement-breakpoint
CREATE TABLE "support_questions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"profile_id" uuid NOT NULL,
	"order_id" uuid,
	"question" text NOT NULL,
	"answer" text,
	"answered_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "guide_orders" ADD COLUMN "listing_nudge_10_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "guide_orders" ADD COLUMN "listing_nudge_30_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "profiles" ADD COLUMN "ref_code" text;--> statement-breakpoint
ALTER TABLE "profiles" ADD COLUMN "listing_nudge_opt_out" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "projects" ADD COLUMN "source_guide_order_id" uuid;--> statement-breakpoint
ALTER TABLE "support_questions" ADD CONSTRAINT "support_questions_profile_id_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "support_questions" ADD CONSTRAINT "support_questions_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "attribution_visits_code_idx" ON "attribution_visits" USING btree ("code","created_at");--> statement-breakpoint
CREATE INDEX "support_questions_profile_idx" ON "support_questions" USING btree ("profile_id","created_at");--> statement-breakpoint
ALTER TABLE "projects" ADD CONSTRAINT "projects_source_guide_order_id_guide_orders_id_fk" FOREIGN KEY ("source_guide_order_id") REFERENCES "public"."guide_orders"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "projects_source_guide_idx" ON "projects" USING btree ("source_guide_order_id");