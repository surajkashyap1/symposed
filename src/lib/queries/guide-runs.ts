import { and, asc, desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import {
  guideProsperoChecks,
  guideRunCandidates,
  guideRuns,
  guideScreenedPapers,
  guideSearches,
  guideTieBreaks,
  guideVerifications,
} from "@/db/schema";

export type GateRow = {
  name: string;
  outcome: string;
  value: number | null;
  threshold: number | null;
  detail: string;
};

export type SimilarWork = { title: string; url: string; score: number };

// Everything Stage 6 shows for an order's latest pipeline run, or null if the
// pipeline has not run for it yet. The draft docx itself is not loaded here
// (it is downloaded through its own route).
export async function latestRunReview(orderId: string) {
  const [run] = await db
    .select({
      id: guideRuns.id,
      status: guideRuns.status,
      title: guideRuns.title,
      publicationType: guideRuns.publicationType,
      axis: guideRuns.axis,
      contactReason: guideRuns.contactReason,
      costUsd: guideRuns.costUsd,
      results: guideRuns.results,
      metrics: guideRuns.metrics,
      startedAt: guideRuns.startedAt,
      finishedAt: guideRuns.finishedAt,
      hasDocx: sql<boolean>`${guideRuns.guideDocx} is not null`,
    })
    .from(guideRuns)
    .where(eq(guideRuns.orderId, orderId))
    .orderBy(desc(guideRuns.startedAt))
    .limit(1);
  if (!run) return null;

  const [winner, prospero, tieBreak, searches, statusCounts, verifications] =
    await Promise.all([
      run.title
        ? db
            .select()
            .from(guideRunCandidates)
            .where(and(eq(guideRunCandidates.runId, run.id), eq(guideRunCandidates.title, run.title)))
            .limit(1)
        : Promise.resolve([]),
      db.select().from(guideProsperoChecks).where(eq(guideProsperoChecks.runId, run.id)).limit(1),
      db.select().from(guideTieBreaks).where(eq(guideTieBreaks.runId, run.id)).limit(1),
      db
        .select()
        .from(guideSearches)
        .where(eq(guideSearches.runId, run.id))
        .orderBy(asc(guideSearches.runAt)),
      db
        .select({ status: guideScreenedPapers.status, n: sql<number>`count(*)::int` })
        .from(guideScreenedPapers)
        .where(eq(guideScreenedPapers.runId, run.id))
        .groupBy(guideScreenedPapers.status),
      db
        .select()
        .from(guideVerifications)
        .where(eq(guideVerifications.runId, run.id))
        .orderBy(desc(guideVerifications.createdAt)),
    ]);

  const results = (run.results ?? {}) as Record<string, unknown>;
  const guide = (results.guide ?? {}) as Record<string, unknown>;
  return {
    run,
    winner: winner[0] ?? null,
    gates: ((winner[0]?.gates ?? []) as GateRow[]),
    prospero: prospero[0] ?? null,
    tieBreak: tieBreak[0] ?? null,
    searches,
    statusCounts: Object.fromEntries(statusCounts.map((r) => [r.status, r.n])),
    verifications,
    rationale: typeof guide.rationale === "string" ? guide.rationale : "",
    similar: (guide.similar_work ?? []) as SimilarWork[],
    warnings: (guide.warnings_for_reviewer ?? []) as string[],
    error: typeof results.error === "string" ? results.error : "",
  };
}

export type RunReview = NonNullable<Awaited<ReturnType<typeof latestRunReview>>>;
