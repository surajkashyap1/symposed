import { and, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { platformConfig, projects } from "@/db/schema";

// Amendment §8: member benefits are computed from CURRENT STATE, never from a
// past event (§8.7). We never store "this user once posted"; we check whether
// they own a live listing at the moment a benefit is used, so an expired
// listing returns the user to standard entitlements automatically.

export type PlatformConfig = typeof platformConfig.$inferSelect;

export async function getPlatformConfig(): Promise<PlatformConfig> {
  const [cfg] = await db.select().from(platformConfig).limit(1);
  if (!cfg)
    throw new Error(
      "platform_config row missing. Run drizzle/manual/0007_platform_seed.sql"
    );
  return cfg;
}

export type MemberTier = "standard" | "lister" | "guide_lister";

export type Entitlements = {
  tier: MemberTier;
  hasLiveListing: boolean;
  isGuideLister: boolean;
  weeklyCredits: number;
  supportAllowance: number;
  supportResponseDays: number;
};

export const TIER_LABEL: Record<MemberTier, string> = {
  standard: "Standard member",
  lister: "Project lister",
  guide_lister: "Guide lister",
};

// A "live listing" is a project the user owns that is currently active. A
// listing marked filled or completed still counts as active for entitlement
// purposes (§8.7: do not penalise success); only draft/closed do not count.
export async function getEntitlements(userId: string): Promise<Entitlements> {
  const cfg = await getPlatformConfig();

  // Optional anti-gaming (§8.7): benefits vest only once a listing has been
  // live this many days. 0 = off (the launch default).
  const vested =
    cfg.vestListingDays > 0
      ? sql`${projects.createdAt} <= now() - make_interval(days => ${cfg.vestListingDays})`
      : sql`true`;

  const [row] = await db
    .select({
      live: sql<number>`count(*)::int`,
      guide: sql<number>`count(*) filter (where ${projects.sourceGuideOrderId} is not null)::int`,
    })
    .from(projects)
    .where(
      and(
        eq(projects.ownerId, userId),
        sql`${projects.status} in ('open', 'in_progress', 'completed')`,
        vested
      )
    );

  const hasLiveListing = row.live > 0;
  const isGuideLister = row.guide > 0;
  const tier: MemberTier = isGuideLister
    ? "guide_lister"
    : hasLiveListing
      ? "lister"
      : "standard";
  const weeklyCredits =
    tier === "guide_lister"
      ? cfg.creditsGuideLister
      : tier === "lister"
        ? cfg.creditsLister
        : cfg.creditsStandard;

  return {
    tier,
    hasLiveListing,
    isGuideLister,
    weeklyCredits,
    supportAllowance: cfg.supportAllowance,
    supportResponseDays: cfg.supportResponseDays,
  };
}
