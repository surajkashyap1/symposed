import { eq } from "drizzle-orm";
import { db } from "@/db";
import { badges, userBadges } from "@/db/schema";

// Badge catalogue (ROADMAP §5). Definitions are upserted lazily on first award,
// so no separate seed migration is needed.
export const BADGE_DEFS = {
  new_researcher: {
    code: "new_researcher",
    name: "New Researcher",
    description: "Starting out, no completed projects yet.",
  },
  research_mentor: {
    code: "research_mentor",
    name: "Research Mentor",
    description: "Accepts and supports beginners on projects.",
  },
  project_lead: {
    code: "project_lead",
    name: "Project Lead",
    description: "Has led a research project to completion.",
  },
} as const;

export type BadgeCode = keyof typeof BADGE_DEFS;

// Research Mentor is time-limited but kept as history (ROADMAP §5 / plan §11).
export const MENTOR_VALIDITY_MONTHS = 6;

async function ensureBadgeId(code: BadgeCode): Promise<number> {
  const def = BADGE_DEFS[code];
  await db
    .insert(badges)
    .values({ code: def.code, name: def.name, description: def.description })
    .onConflictDoNothing();
  const [row] = await db
    .select({ id: badges.id })
    .from(badges)
    .where(eq(badges.code, code))
    .limit(1);
  return row.id;
}

// Award (or refresh) a badge. Re-awarding updates the timestamp/expiry so the
// row persists as history even after a mentor badge lapses.
export async function awardBadge(
  profileId: string,
  code: BadgeCode,
  expiresAt?: Date
): Promise<void> {
  const badgeId = await ensureBadgeId(code);
  await db
    .insert(userBadges)
    .values({ profileId, badgeId, expiresAt: expiresAt ?? null })
    .onConflictDoUpdate({
      target: [userBadges.profileId, userBadges.badgeId],
      set: { awardedAt: new Date(), expiresAt: expiresAt ?? null },
    });
}

export type DisplayBadge = {
  code: string;
  name: string;
  description: string | null;
  active: boolean;
  expiresAt: Date | null;
};

// Unified badge list for a profile: the derived New Researcher flag plus any
// awarded user_badges (with active/expired state for time-limited ones).
export async function getBadgesForProfile(
  profileId: string,
  isNewResearcher: boolean
): Promise<DisplayBadge[]> {
  const rows = await db
    .select({
      code: badges.code,
      name: badges.name,
      description: badges.description,
      expiresAt: userBadges.expiresAt,
    })
    .from(userBadges)
    .innerJoin(badges, eq(badges.id, userBadges.badgeId))
    .where(eq(userBadges.profileId, profileId));

  const now = Date.now();
  const list: DisplayBadge[] = rows.map((r) => ({
    code: r.code,
    name: r.name,
    description: r.description,
    active: !r.expiresAt || r.expiresAt.getTime() > now,
    expiresAt: r.expiresAt,
  }));

  if (isNewResearcher) {
    list.unshift({
      code: BADGE_DEFS.new_researcher.code,
      name: BADGE_DEFS.new_researcher.name,
      description: BADGE_DEFS.new_researcher.description,
      active: true,
      expiresAt: null,
    });
  }
  return list;
}
