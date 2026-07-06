import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { getProjectRow } from "@/lib/queries/projects";
import { getRankedApplicantsForProject } from "@/lib/queries/applications";
import { setApplicationStatus } from "@/app/applications/actions";
import { STATUS_LABELS, STATUS_BADGE_CLASS } from "@/lib/application-meta";
import { CAREER_STAGES } from "@/lib/profile";
import type { RankingResult } from "@/lib/ranking";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

function stageLabel(value: string) {
  return CAREER_STAGES.find((s) => s.value === value)?.label ?? value;
}

function ScoreBreakdown({ ranking }: { ranking: RankingResult }) {
  return (
    <details className="rounded-md border bg-muted/30 px-3 py-2 text-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="font-medium">Fairness score</span>
        <span className="font-semibold">{ranking.score}/100</span>
      </summary>
      <dl className="mt-3 flex flex-col gap-1.5">
        {ranking.components.map((c) => (
          <div key={c.key} className="flex items-center gap-3">
            <dt className="w-36 shrink-0 text-xs text-muted-foreground">
              {c.label}
            </dt>
            <div
              className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary"
              role="img"
              aria-label={`${c.label}: ${Math.round(c.value * 100)} percent`}
            >
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.round(c.value * 100)}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
              {Math.round(c.value * 100)}%
            </span>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-muted-foreground">
        A guide, not a verdict. Beginners are boosted and prior experience is
        weighted lightly. You decide.
      </p>
    </details>
  );
}

export default async function ApplicantsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ anon?: string }>;
}) {
  const { id } = await params;
  const { anon } = await searchParams;
  const anonymous = anon === "1";
  const user = await requireUser();
  const project = await getProjectRow(id);
  if (!project) notFound();
  if (project.ownerId !== user.id) redirect(`/projects/${id}`);

  const applicants = await getRankedApplicantsForProject(id, {
    isBeginnerFriendly: project.isBeginnerFriendly,
    specialty: project.specialty,
    roleCategory: project.roleCategory,
  });

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <Link
        href={`/projects/${id}`}
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Back to listing
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Applicants</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {project.title} · {applicants.length} application
            {applicants.length === 1 ? "" : "s"}
          </p>
        </div>
        {applicants.length > 0 && (
          <Link
            href={anonymous ? `/projects/${id}/applicants` : `/projects/${id}/applicants?anon=1`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {anonymous ? "Show identities" : "Review anonymously"}
          </Link>
        )}
      </div>

      {anonymous && (
        <p className="mt-4 rounded-md border border-dashed bg-muted/30 px-4 py-2 text-sm text-muted-foreground">
          Anonymous mode hides names, universities and verification so you can
          judge on motivation, fit and fairness first (plan §11).
        </p>
      )}

      {applicants.length === 0 ? (
        <div className="mt-10 rounded-lg border border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">No applications yet.</p>
        </div>
      ) : (
        <ul className="mt-8 flex flex-col gap-4">
          {applicants.map((a, i) => (
            <li key={a.id}>
              <Card>
                <CardContent className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      {anonymous ? (
                        <p className="font-medium">
                          Applicant {String.fromCharCode(65 + (i % 26))}
                        </p>
                      ) : (
                        <p className="font-medium">
                          <Link
                            href={`/profile/${a.applicantId}`}
                            // One per applicant: avoid the dynamic-prefetch
                            // churn that starves the accept/reject refresh.
                            prefetch={false}
                            className="hover:underline"
                          >
                            {a.applicantName ?? "Member"}
                          </Link>
                          {a.applicantVerified && (
                            <span className="ml-1 text-success" title="Verified">
                              ✓
                            </span>
                          )}
                        </p>
                      )}
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {anonymous
                          ? `Applied ${a.createdAt.toLocaleDateString("en-GB")}`
                          : `${stageLabel(a.applicantCareerStage)}${
                              a.applicantUniversity ? ` · ${a.applicantUniversity}` : ""
                            } · applied ${a.createdAt.toLocaleDateString("en-GB")}`}
                      </p>
                      {a.applicantNewResearcher && (
                        <Badge variant="secondary" className="mt-2">
                          New researcher
                        </Badge>
                      )}
                    </div>
                    <Badge className={STATUS_BADGE_CLASS[a.status]}>
                      {STATUS_LABELS[a.status]}
                    </Badge>
                  </div>

                  <ScoreBreakdown ranking={a.ranking} />

                  <dl className="flex flex-col gap-3 text-sm">
                    <div>
                      <dt className="text-xs font-medium text-muted-foreground">
                        Motivation
                      </dt>
                      <dd className="mt-0.5 whitespace-pre-wrap">{a.motivation}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium text-muted-foreground">
                        Suitability
                      </dt>
                      <dd className="mt-0.5 whitespace-pre-wrap">{a.suitability}</dd>
                    </div>
                    {a.skillsSummary && (
                      <div>
                        <dt className="text-xs font-medium text-muted-foreground">
                          Application skills
                        </dt>
                        <dd className="mt-0.5 whitespace-pre-wrap">
                          {a.skillsSummary}
                        </dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-xs font-medium text-muted-foreground">
                        Time available for this project
                      </dt>
                      <dd className="mt-0.5">
                        {a.hoursPerWeek != null
                          ? `${a.hoursPerWeek} hrs/week`
                          : "Not specified"}
                      </dd>
                    </div>
                    {!anonymous && (
                      <>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground">
                            Profile skills
                          </dt>
                          <dd className="mt-0.5">
                            {a.applicantSkills ?? "Not specified"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground">
                            Looking for project types
                          </dt>
                          <dd className="mt-0.5">
                            {a.applicantPreferredProjectTypes ?? "Not specified"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground">
                            Preferred specialties
                          </dt>
                          <dd className="mt-0.5">
                            {a.applicantPreferredSpecialties ?? "Not specified"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs font-medium text-muted-foreground">
                            Profile availability and certifications
                          </dt>
                          <dd className="mt-0.5">
                            {a.applicantAvailabilityHoursPerWeek != null
                              ? `${a.applicantAvailabilityHoursPerWeek} hrs/week`
                              : "Availability not specified"}
                            {" · "}
                            {a.applicantCertificationCount} certification
                            {a.applicantCertificationCount === 1 ? "" : "s"}
                          </dd>
                        </div>
                      </>
                    )}
                  </dl>

                  {a.status !== "withdrawn" && (
                    <div className="flex flex-wrap gap-2">
                      {a.status !== "shortlisted" && a.status !== "accepted" && (
                        <StatusButton id={a.id} projectId={id} status="shortlisted" label="Shortlist" />
                      )}
                      {a.status !== "accepted" && (
                        <StatusButton id={a.id} projectId={id} status="accepted" label="Accept" />
                      )}
                      {a.status !== "rejected" && (
                        <StatusButton id={a.id} projectId={id} status="rejected" label="Reject" variant="ghost" />
                      )}
                      {a.status === "accepted" && !anonymous && (
                        <Link
                          href={`/projects/${id}/review/${a.applicantId}`}
                          className={buttonVariants({ variant: "outline", size: "sm" })}
                        >
                          Review
                        </Link>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function StatusButton({
  id,
  projectId,
  status,
  label,
  variant = "outline",
}: {
  id: string;
  projectId: string;
  status: string;
  label: string;
  variant?: "outline" | "ghost";
}) {
  return (
    <form action={setApplicationStatus}>
      <input type="hidden" name="id" value={id} />
      <input type="hidden" name="projectId" value={projectId} />
      <input type="hidden" name="status" value={status} />
      <Button type="submit" size="sm" variant={variant}>
        {label}
      </Button>
    </form>
  );
}
