CREATE TYPE "public"."open_guide_type" AS ENUM('systematic_review', 'literature_review');--> statement-breakpoint
CREATE TABLE "open_guides" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"reference" text NOT NULL,
	"specialty" text NOT NULL,
	"review_type" "open_guide_type" NOT NULL,
	"description" text NOT NULL,
	"is_available" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "open_guides_reference_unique" UNIQUE("reference")
);
--> statement-breakpoint
CREATE INDEX "open_guides_available_idx" ON "open_guides" USING btree ("is_available","created_at");