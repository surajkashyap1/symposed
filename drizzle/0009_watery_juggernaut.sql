CREATE TYPE "public"."guide_order_status" AS ENUM('submitted', 'paid', 'in_progress', 'delivered', 'refunded');--> statement-breakpoint
CREATE TYPE "public"."guide_review_status" AS ENUM('pending', 'approved', 'rejected', 'removed');--> statement-breakpoint
CREATE TABLE "guide_order_files" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid NOT NULL,
	"path" text NOT NULL,
	"filename" text NOT NULL,
	"content_type" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_orders" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"profile_id" uuid NOT NULL,
	"proforma" text NOT NULL,
	"full_name" text NOT NULL,
	"email" text NOT NULL,
	"status" "guide_order_status" DEFAULT 'submitted' NOT NULL,
	"discount_applied" boolean DEFAULT false NOT NULL,
	"price_at_checkout_pence" integer,
	"price_paid_pence" integer,
	"checkout_started_at" timestamp with time zone,
	"stripe_session_id" text,
	"stripe_payment_intent_id" text,
	"consent_immediate_at" timestamp with time zone,
	"consent_terms_at" timestamp with time zone,
	"consent_ip" text,
	"ip_country" text,
	"billing_country" text,
	"card_country" text,
	"country_mismatch" boolean DEFAULT false NOT NULL,
	"verified_by" text,
	"verified_at" timestamp with time zone,
	"verification_note" text,
	"paid_at" timestamp with time zone,
	"delivered_at" timestamp with time zone,
	"overdue_alerted_at" timestamp with time zone,
	"review_token" text,
	"review_requested_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "guide_orders_review_token_unique" UNIQUE("review_token")
);
--> statement-breakpoint
CREATE TABLE "guide_pricing_config" (
	"id" integer PRIMARY KEY DEFAULT 1 NOT NULL,
	"standard_price_pence" integer DEFAULT 4500 NOT NULL,
	"intro_price_pence" integer DEFAULT 2500 NOT NULL,
	"intro_quantity" integer DEFAULT 10 NOT NULL,
	"blocked_countries" text[] NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "guide_reviews" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"order_id" uuid,
	"reviewer_name" text NOT NULL,
	"reviewer_role" text NOT NULL,
	"reviewer_institution" text,
	"rating" integer NOT NULL,
	"body" text NOT NULL,
	"guide_topic" text,
	"complimentary_guide" boolean DEFAULT false NOT NULL,
	"status" "guide_review_status" DEFAULT 'pending' NOT NULL,
	"published_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "guide_order_files" ADD CONSTRAINT "guide_order_files_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_orders" ADD CONSTRAINT "guide_orders_profile_id_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "guide_reviews" ADD CONSTRAINT "guide_reviews_order_id_guide_orders_id_fk" FOREIGN KEY ("order_id") REFERENCES "public"."guide_orders"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "guide_order_files_order_idx" ON "guide_order_files" USING btree ("order_id");--> statement-breakpoint
CREATE INDEX "guide_orders_profile_idx" ON "guide_orders" USING btree ("profile_id");--> statement-breakpoint
CREATE INDEX "guide_orders_status_idx" ON "guide_orders" USING btree ("status","created_at");--> statement-breakpoint
CREATE INDEX "guide_orders_session_idx" ON "guide_orders" USING btree ("stripe_session_id");--> statement-breakpoint
CREATE INDEX "guide_reviews_status_idx" ON "guide_reviews" USING btree ("status","published_at");