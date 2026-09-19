ALTER TABLE "guide_pricing_config" ALTER COLUMN "intro_quantity" SET DEFAULT 25;--> statement-breakpoint
ALTER TABLE "guide_pricing_config" ADD COLUMN "free_quantity" integer DEFAULT 25 NOT NULL;--> statement-breakpoint
ALTER TABLE "guide_pricing_config" ADD COLUMN "payments_enabled" boolean DEFAULT false NOT NULL;