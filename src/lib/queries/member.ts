import { and, desc, eq, ne, sql } from "drizzle-orm";
import { db } from "@/db";
import { applications, projects, supportQuestions } from "@/db/schema";
import { getEntitlements } from "@/lib/queries/entitlements";

// Amendment §8.3 — the platform records what actually happened, so leadership
// and team coordination become evidence. Symposed confirms only that the
// project existed, who led it, how many joined and when. It never characterises
// the quality of the work and never references "portfolio points".

export type ProjectRecord = {
  led: {
    id: string;
    title: string;
    status: string;
    createdAt: Date;
    updatedAt: Date;
  }[];
  collaboratorsRecruited: number;
  joined: {
    id: string;
    title: string;
    status: string;
    createdAt: Date;
  }[];
};

export async function getProjectRecord(userId: string): Promise<ProjectRecord> {
  const [led, [{ recruited }], joined] = await Promise.all([
    // Projects led (drafts excluded: they are not real listings yet).
    db
      .select({
        id: projects.id,
        title: projects.title,
        status: projects.status,
        createdAt: projects.createdAt,
        updatedAt: projects.updatedAt,
      })
      .from(projects)
      .where(and(eq(projects.ownerId, userId), ne(projects.status, "draft")))
      .orderBy(desc(projects.createdAt)),
    // Collaborators recruited through the platform = accepted applications on
    // the user's own projects.
    db
      .select({ recruited: sql<number>`count(*)::int` })
      .from(applications)
      .innerJoin(projects, eq(projects.id, applications.projectId))
      .where(and(eq(projects.ownerId, userId), eq(applications.status, "accepted"))),
    // Projects joined as a collaborator, kept distinct from projects led.
    db
      .select({
        id: projects.id,
        title: projects.title,
        status: projects.status,
        createdAt: projects.createdAt,
      })
      .from(applications)
      .innerJoin(projects, eq(projects.id, applications.projectId))
      .where(
        and(
          eq(applications.applicantId, userId),
          eq(applications.status, "accepted"),
          ne(projects.ownerId, userId)
        )
      )
      .orderBy(desc(projects.createdAt)),
  ]);

  return { led, collaboratorsRecruited: recruited, joined };
}

// Amendment §8.8 — bounded direct support. The allowance is stated up front and
// enforced in the product. Eligibility follows from having a live listing.
export type SupportState = {
  eligible: boolean;
  allowance: number;
  used: number;
  remaining: number;
  responseDays: number;
  questions: {
    id: string;
    question: string;
    answer: string | null;
    createdAt: Date;
    answeredAt: Date | null;
  }[];
};

export async function getSupportState(userId: string): Promise<SupportState> {
  const [ent, rows] = await Promise.all([
    getEntitlements(userId),
    db
      .select({
        id: supportQuestions.id,
        question: supportQuestions.question,
        answer: supportQuestions.answer,
        createdAt: supportQuestions.createdAt,
        answeredAt: supportQuestions.answeredAt,
      })
      .from(supportQuestions)
      .where(eq(supportQuestions.profileId, userId))
      .orderBy(desc(supportQuestions.createdAt)),
  ]);

  const used = rows.length;
  return {
    eligible: ent.hasLiveListing,
    allowance: ent.supportAllowance,
    used,
    remaining: Math.max(0, ent.supportAllowance - used),
    responseDays: ent.supportResponseDays,
    questions: rows,
  };
}

// Admin queue: unanswered support questions, oldest first (batched with the
// weekly run per §8.8).
export async function listPendingSupportQuestions() {
  return db
    .select()
    .from(supportQuestions)
    .where(sql`${supportQuestions.answer} is null`)
    .orderBy(supportQuestions.createdAt);
}
