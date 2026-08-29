import { and, arrayContains, desc, eq, gt, gte, ilike, or, sql } from "drizzle-orm";
import { db } from "@/db";
import { availabilityListings, listingContacts, profiles } from "@/db/schema";

// Queries for the Available for Projects reverse board (docs spec §5).
// A listing is live when status = 'active' AND not past its 60-day expiry —
// expiry is enforced here at query time, so stale listings vanish without
// needing a cron to flip a status column.

const liveConds = () => [
  eq(availabilityListings.status, "active"),
  gt(availabilityListings.expiresAt, sql`now()`),
];

const listColumns = {
  id: availabilityListings.id,
  profileId: availabilityListings.profileId,
  headline: availabilityListings.headline,
  displayInitialsOnly: availabilityListings.displayInitialsOnly,
  showInstitution: availabilityListings.showInstitution,
  region: availabilityListings.region,
  specialties: availabilityListings.specialties,
  skills: availabilityListings.skills,
  hoursPerWeek: availabilityListings.hoursPerWeek,
  availableFrom: availabilityListings.availableFrom,
  previousPublications: availabilityListings.previousPublications,
  lookingFor: availabilityListings.lookingFor,
  updatedAt: availabilityListings.updatedAt,
  ownerName: profiles.fullName,
  ownerUniversity: profiles.university,
  ownerCareerStage: profiles.careerStage,
  ownerVerified: profiles.isVerified,
};

export type AvailabilityListItem = {
  id: string;
  profileId: string;
  headline: string;
  displayInitialsOnly: boolean;
  showInstitution: boolean;
  region: string | null;
  specialties: string | null;
  skills: string[];
  hoursPerWeek: number | null;
  availableFrom: string | null;
  previousPublications: string | null;
  lookingFor: string;
  updatedAt: Date;
  ownerName: string | null;
  ownerUniversity: string | null;
  ownerCareerStage: string | null;
  ownerVerified: boolean | null;
};

export type ListAvailabilityOptions = {
  q?: string;
  specialty?: string;
  skill?: string;
  careerStage?: string;
  region?: string;
  minHours?: number;
  page?: number;
};

export const AVAILABILITY_PAGE_SIZE = 12;

export async function listAvailability(opts: ListAvailabilityOptions): Promise<{
  items: AvailabilityListItem[];
  total: number;
  page: number;
  pageCount: number;
}> {
  const conds = [...liveConds()];

  if (opts.q) {
    conds.push(
      or(
        ilike(availabilityListings.headline, `%${opts.q}%`),
        ilike(availabilityListings.lookingFor, `%${opts.q}%`),
        ilike(availabilityListings.specialties, `%${opts.q}%`)
      )!
    );
  }
  if (opts.specialty)
    conds.push(ilike(availabilityListings.specialties, `%${opts.specialty}%`));
  if (opts.skill) conds.push(arrayContains(availabilityListings.skills, [opts.skill]));
  if (opts.region) conds.push(ilike(availabilityListings.region, `%${opts.region}%`));
  if (opts.minHours != null)
    conds.push(gte(availabilityListings.hoursPerWeek, opts.minHours));

  const stageCond = opts.careerStage
    ? eq(profiles.careerStage, opts.careerStage as typeof profiles.careerStage._.data)
    : undefined;

  const where = stageCond ? and(...conds, stageCond) : and(...conds);

  const [{ total }] = await db
    .select({ total: sql<number>`count(*)::int` })
    .from(availabilityListings)
    .leftJoin(profiles, eq(profiles.id, availabilityListings.profileId))
    .where(where);

  const pageCount = Math.max(1, Math.ceil(total / AVAILABILITY_PAGE_SIZE));
  const page = Math.min(Math.max(1, Math.floor(opts.page ?? 1)), pageCount);

  const items = await db
    .select(listColumns)
    .from(availabilityListings)
    .leftJoin(profiles, eq(profiles.id, availabilityListings.profileId))
    .where(where)
    // Most recently updated first — renewal bumps a listing to the top.
    .orderBy(desc(availabilityListings.updatedAt), desc(availabilityListings.id))
    .limit(AVAILABILITY_PAGE_SIZE)
    .offset((page - 1) * AVAILABILITY_PAGE_SIZE);

  return { items, total, page, pageCount };
}

// Count of live listings, for the cross-link rule on /projects (spec §5.4).
export async function countLiveAvailability(): Promise<number> {
  const [{ total }] = await db
    .select({ total: sql<number>`count(*)::int` })
    .from(availabilityListings)
    .where(and(...liveConds()));
  return total;
}

// The signed-in user's own listing in any state (drives the manage strip).
// Liveness is computed in SQL so render code never needs an impure clock read.
export async function getMyListing(profileId: string) {
  const [row] = await db
    .select({
      listing: availabilityListings,
      isLive: sql<boolean>`(
        ${availabilityListings.status} = 'active'
        and ${availabilityListings.expiresAt} > now()
      )`,
    })
    .from(availabilityListings)
    .where(eq(availabilityListings.profileId, profileId))
    .limit(1);
  if (!row) return null;
  return { ...row.listing, isLive: row.isLive };
}

// A single live listing with owner info, for the contact page.
export async function getLiveListing(id: string): Promise<AvailabilityListItem | null> {
  const [row] = await db
    .select(listColumns)
    .from(availabilityListings)
    .leftJoin(profiles, eq(profiles.id, availabilityListings.profileId))
    .where(and(eq(availabilityListings.id, id), ...liveConds()))
    .limit(1);
  return row ?? null;
}

// Messages sent in the last 24h, for the 10-per-day relay rate limit.
export async function countRecentContacts(senderId: string): Promise<number> {
  const [{ total }] = await db
    .select({ total: sql<number>`count(*)::int` })
    .from(listingContacts)
    .where(
      and(
        eq(listingContacts.senderId, senderId),
        gt(listingContacts.createdAt, sql`now() - interval '24 hours'`)
      )
    );
  return total;
}
