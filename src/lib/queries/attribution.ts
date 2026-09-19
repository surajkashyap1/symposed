import { and, eq, gte, lte, ne, sql, type AnyColumn, type SQL } from "drizzle-orm";
import { db } from "@/db";
import {
  attributionVisits,
  guideOrders,
  profiles,
  projects,
  referralCodes,
} from "@/db/schema";
import { DIRECT } from "@/lib/attribution";

// Per-code channel-attribution report (spec §9.2): the whole funnel, not just
// raw totals, so a channel bringing many signups and no guide requests reads as
// worse than a smaller one that converts.

export type AttributionRow = {
  code: string;
  label: string | null;
  visits: number;
  signups: number;
  requests: number;
  delivered: number;
  listings: number;
};

export type DateRange = { from?: Date; to?: Date };

function between(col: AnyColumn, range: DateRange): SQL[] {
  const conds: SQL[] = [];
  if (range.from) conds.push(gte(col, range.from));
  if (range.to) conds.push(lte(col, range.to));
  return conds;
}

// A profile's channel, defaulting the many pre-attribution rows (and any null)
// to "direct" so they aggregate into one bucket rather than vanishing.
const profileCode = sql<string>`coalesce(${profiles.refCode}, ${DIRECT})`;

export async function getAttributionReport(
  range: DateRange = {}
): Promise<AttributionRow[]> {
  const [codes, visits, signups, orders, listings] = await Promise.all([
    db.select().from(referralCodes),

    db
      .select({
        code: attributionVisits.code,
        n: sql<number>`count(*)::int`,
      })
      .from(attributionVisits)
      .where(and(...between(attributionVisits.createdAt, range)))
      .groupBy(attributionVisits.code),

    db
      .select({ code: profileCode, n: sql<number>`count(*)::int` })
      .from(profiles)
      .where(and(...between(profiles.createdAt, range)))
      .groupBy(profileCode),

    // Guide requests and deliveries as a request-date cohort: both counted
    // against the order's channel so the funnel stays consistent.
    db
      .select({
        code: profileCode,
        requests: sql<number>`count(*)::int`,
        delivered: sql<number>`count(*) filter (where ${guideOrders.deliveredAt} is not null)::int`,
      })
      .from(guideOrders)
      .innerJoin(profiles, eq(profiles.id, guideOrders.profileId))
      .where(and(...between(guideOrders.createdAt, range)))
      .groupBy(profileCode),

    // Listings published = projects that left draft (§9.2).
    db
      .select({ code: profileCode, n: sql<number>`count(*)::int` })
      .from(projects)
      .innerJoin(profiles, eq(profiles.id, projects.ownerId))
      .where(and(ne(projects.status, "draft"), ...between(projects.createdAt, range)))
      .groupBy(profileCode),
  ]);

  const rows = new Map<string, AttributionRow>();
  const row = (code: string): AttributionRow => {
    let r = rows.get(code);
    if (!r) {
      r = { code, label: null, visits: 0, signups: 0, requests: 0, delivered: 0, listings: 0 };
      rows.set(code, r);
    }
    return r;
  };

  // Seed every administrator-created code so a channel with zero traffic still
  // shows up (it is a real, actionable "this one is not working" signal).
  for (const c of codes) row(c.code).label = c.label;
  for (const v of visits) row(v.code).visits = v.n;
  for (const s of signups) row(s.code).signups = s.n;
  for (const o of orders) {
    const r = row(o.code);
    r.requests = o.requests;
    r.delivered = o.delivered;
  }
  for (const l of listings) row(l.code).listings = l.n;

  // "direct" last, real codes by total activity so the useful ones sit on top.
  return [...rows.values()].sort((a, b) => {
    if (a.code === DIRECT) return 1;
    if (b.code === DIRECT) return -1;
    const av = a.visits + a.signups + a.requests;
    const bv = b.visits + b.signups + b.requests;
    return bv - av || a.code.localeCompare(b.code);
  });
}

export async function listReferralCodes() {
  return db.select().from(referralCodes).orderBy(referralCodes.code);
}
