ALTER TYPE "public"."verification_type" ADD VALUE 'login_email';--> statement-breakpoint
CREATE TABLE "app_errors" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"message" text NOT NULL,
	"digest" text,
	"stack" text,
	"path" text,
	"method" text,
	"route_path" text,
	"route_type" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "profiles" ADD COLUMN "email_confirmed_at" timestamp with time zone;--> statement-breakpoint
CREATE INDEX "app_errors_created_idx" ON "app_errors" USING btree ("created_at");