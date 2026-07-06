import { and, desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { reviews, applications, projects, profiles } from "@/db/schema";
import type { ReviewDirection } from "@/lib/review-meta";

export async function isAcceptedMember(
  projectId: string,
  memberId: string
): Promise<boolean> {
  const rows = await db
    .select({ id: applications.id })
    .from(applications)
    .where(
      and(
        eq(applications.projectId, projectId),
        eq(applications.applicantId, memberId),
        eq(applications.status, "accepted")
      )
    )
    .limit(1);
  return rows.length > 0;
}

export type ReviewableContext = {
  direction: ReviewDirection;
  projectTitle: string;
  isBeginnerFriendly: boolean;
  ownerId: string;
  alreadyReviewed: boolean;
  revieweeName: string | null;
};

// Determines whether `reviewer` may review `reviewee` for this project, and in
// which direction. Reviews require an accepted applicant↔owner relationship.
export async function getReviewableContext(
  projectId: string,
  reviewerId: string,
  revieweeId: string
): Promise<ReviewableContext | null> {
  if (reviewerId === revieweeId) return null;

  const [project] = await db
    .select({
      ownerId: projects.ownerId,
      title: projects.title,
      bf: projects.isBeginnerFriendly,
    })
    .from(projects)
    .where(eq(projects.id, projectId))
    .limit(1);
  if (!project) return null;

  let direction: ReviewDirection | null = null;
  if (reviewerId === project.ownerId) {
    if (await isAcceptedMember(projectId, revieweeId))
      direction = "supervisor_to_member";
  } else if (revieweeId === project.ownerId) {
    if (await isAcceptedMember(projectId, reviewerId))
      direction = "member_to_supervisor";
  }
  if (!direction) return null;

  const [existing] = await db
    .select({ id: reviews.id })
    .from(reviews)
    .where(
      and(
        eq(reviews.projectId, projectId),
        eq(reviews.reviewerId, reviewerId),
        eq(reviews.revieweeId, revieweeId)
      )
    )
    .limit(1);
  const [reviewee] = await db
    .select({ name: profiles.fullName })
    .from(profiles)
    .where(eq(profiles.id, revieweeId))
    .limit(1);

  return {
    direction,
    projectTitle: project.title,
    isBeginnerFriendly: project.bf,
    ownerId: project.ownerId,
    alreadyReviewed: !!existing,
    revieweeName: reviewee?.name ?? null,
  };
}

export type RatingSummary = {
  memberAvg: number | null;
  memberCount: number;
  supervisorAvg: number | null;
  supervisorCount: number;
};

export async function getRatingSummary(profileId: string): Promise<RatingSummary> {
  const rows = await db
    .select({
      direction: reviews.direction,
      avg: sql<string | null>`avg(${reviews.ratingOverall})`,
      n: sql<number>`count(*)::int`,
    })
    .from(reviews)
    .where(eq(reviews.revieweeId, profileId))
    .groupBy(reviews.direction);

  const out: RatingSummary = {
    memberAvg: null,
    memberCount: 0,
    supervisorAvg: null,
    supervisorCount: 0,
  };
  for (const r of rows) {
    if (r.direction === "supervisor_to_member") {
      out.memberAvg = r.avg ? Number(r.avg) : null;
      out.memberCount = r.n;
    } else {
      out.supervisorAvg = r.avg ? Number(r.avg) : null;
      out.supervisorCount = r.n;
    }
  }
  return out;
}

export type ProfileReview = {
  id: string;
  direction: ReviewDirection;
  ratingOverall: string;
  comment: string | null;
  createdAt: Date;
  projectTitle: string | null;
  reviewerName: string | null;
  isAnonymous: boolean;
};

// Newest reviews shown on a profile; the rating summary covers the full
// history, so the page stays bounded however many reviews someone earns.
const PROFILE_REVIEWS_LIMIT = 30;

export async function getReviewsForProfile(
  profileId: string
): Promise<ProfileReview[]> {
  const rows = await db
    .select({
      id: reviews.id,
      direction: reviews.direction,
      ratingOverall: reviews.ratingOverall,
      comment: reviews.comment,
      createdAt: reviews.createdAt,
      isAnonymous: reviews.isAnonymous,
      projectTitle: projects.title,
      reviewerName: profiles.fullName,
    })
    .from(reviews)
    .leftJoin(projects, eq(projects.id, reviews.projectId))
    .leftJoin(profiles, eq(profiles.id, reviews.reviewerId))
    .where(eq(reviews.revieweeId, profileId))
    .orderBy(desc(reviews.createdAt))
    .limit(PROFILE_REVIEWS_LIMIT);

  // Honour anonymous reviews by stripping the reviewer's name.
  return rows.map((r) => ({
    ...r,
    reviewerName: r.isAnonymous ? null : r.reviewerName,
  }));
}

// Reliability score = average overall rating from supervisors (ROADMAP §5).
export async function recomputeReliability(profileId: string): Promise<void> {
  const [agg] = await db
    .select({ avg: sql<string | null>`avg(${reviews.ratingOverall})` })
    .from(reviews)
    .where(
      and(
        eq(reviews.revieweeId, profileId),
        eq(reviews.direction, "supervisor_to_member")
      )
    );
  await db
    .update(profiles)
    .set({ reliabilityScore: agg?.avg ?? null })
    .where(eq(profiles.id, profileId));
}
