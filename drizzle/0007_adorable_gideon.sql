CREATE TYPE "public"."availability_listing_status" AS ENUM('active', 'found_project', 'removed');--> statement-breakpoint
ALTER TYPE "public"."report_target_type" ADD VALUE 'availability_listing';--> statement-breakpoint
CREATE TABLE "availability_listings" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"profile_id" uuid NOT NULL,
	"headline" text NOT NULL,
	"display_initials_only" boolean DEFAULT false NOT NULL,
	"show_institution" boolean DEFAULT true NOT NULL,
	"region" text,
	"specialties" text,
	"skills" text[] NOT NULL,
	"hours_per_week" integer,
	"available_from" date,
	"previous_publications" text,
	"looking_for" text NOT NULL,
	"status" "availability_listing_status" DEFAULT 'active' NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"renewal_emailed_at" timestamp with time zone,
	"found_project_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "availability_listings_profile_id_unique" UNIQUE("profile_id")
);
--> statement-breakpoint
CREATE TABLE "listing_contacts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"listing_id" uuid NOT NULL,
	"sender_id" uuid NOT NULL,
	"recipient_id" uuid NOT NULL,
	"body" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "availability_listings" ADD CONSTRAINT "availability_listings_profile_id_profiles_id_fk" FOREIGN KEY ("profile_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "listing_contacts" ADD CONSTRAINT "listing_contacts_listing_id_availability_listings_id_fk" FOREIGN KEY ("listing_id") REFERENCES "public"."availability_listings"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "listing_contacts" ADD CONSTRAINT "listing_contacts_sender_id_profiles_id_fk" FOREIGN KEY ("sender_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "listing_contacts" ADD CONSTRAINT "listing_contacts_recipient_id_profiles_id_fk" FOREIGN KEY ("recipient_id") REFERENCES "public"."profiles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "availability_listings_board_idx" ON "availability_listings" USING btree ("status","expires_at","updated_at");--> statement-breakpoint
CREATE INDEX "listing_contacts_sender_time_idx" ON "listing_contacts" USING btree ("sender_id","created_at");--> statement-breakpoint
CREATE INDEX "listing_contacts_listing_idx" ON "listing_contacts" USING btree ("listing_id");