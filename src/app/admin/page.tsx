import Link from "next/link";
import { desc, eq, inArray } from "drizzle-orm";
import { db } from "@/db";
import { appErrors, contactMessages, listingQuestions, profiles, projects, reports } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { getMetrics } from "@/lib/queries/metrics";
import { unpublishProject, removeQuestion, resolveReport } from "@/app/admin/actions";
import { AdminNav } from "@/components/admin-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Admin-only metrics. Access is gated by the ADMIN_EMAILS env var (comma-
// separated). If unset, nobody can view it — returns 404 rather than leaking
// that the page exists.
export default async function AdminPage() {
  await requireAdmin();

  const [m, recentErrors, openReports, recentContact] = await Promise.all([
    getMetrics(),
    db.select().from(appErrors).orderBy(desc(appErrors.createdAt)).limit(25),
    db.select().from(reports).where(eq(reports.status, "open")).orderBy(desc(reports.createdAt)).limit(50),
    db.select().from(contactMessages).orderBy(desc(contactMessages.createdAt)).limit(25),
  ]);

  // Previews of reported content so reports can be judged without leaving
  // the page. Missing rows mean the target was already removed.
  const projectIds = openReports.filter((r) => r.targetType === "project").map((r) => r.targetId);
  const questionIds = openReports.filter((r) => r.targetType === "question").map((r) => r.targetId);
  const profileIds = openReports.filter((r) => r.targetType === "profile").map((r) => r.targetId);
  const [reportedProjects, reportedQuestions, reportedProfiles] = await Promise.all([
    projectIds.length
      ? db.select({ id: projects.id, title: projects.title, status: projects.status }).from(projects).where(inArray(projects.id, projectIds))
      : Promise.resolve([]),
    questionIds.length
      ? db.select({ id: listingQuestions.id, question: listingQuestions.question, answer: listingQuestions.answer, projectId: listingQuestions.projectId }).from(listingQuestions).where(inArray(listingQuestions.id, questionIds))
      : Promise.resolve([]),
    profileIds.length
      ? db.select({ id: profiles.id, fullName: profiles.fullName }).from(profiles).where(inArray(profiles.id, profileIds))
      : Promise.resolve([]),
  ]);

  const stats: { label: string; value: string | number; hint?: string }[] = [
    { label: "Total users", value: m.totalUsers },
    { label: "Verified users", value: m.verifiedUsers },
    { label: "Complete profiles", value: `${m.completeProfilePct}%`, hint: "≥ 80% complete" },
    { label: "Active listings", value: m.activeListings },
    { label: "Beginner-friendly (active)", value: m.beginnerFriendlyActive },
    { label: "Total applications", value: m.totalApplications },
    { label: "Accepted (matches)", value: m.acceptedApplications },
    { label: "Apps / active listing", value: m.avgApplicationsPerActiveListing },
    { label: "Reviews written", value: m.totalReviews },
  ];

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <AdminNav current="overview" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">Metrics</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Key launch indicators. Visible to admins only.
      </p>

      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <Card key={s.label}>
            <CardContent>
              <p className="text-sm text-muted-foreground">{s.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{s.value}</p>
              {s.hint && (
                <p className="mt-0.5 text-xs text-muted-foreground">{s.hint}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <h2 className="mt-12 text-lg font-semibold tracking-tight">
        Open reports {openReports.length > 0 && `(${openReports.length})`}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Content and conduct reports awaiting review (Safety Policy §4).
      </p>
      {openReports.length === 0 ? (
        <p className="mt-4 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          No open reports.
        </p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {openReports.map((r) => {
            const project = reportedProjects.find((p) => p.id === r.targetId);
            const question = reportedQuestions.find((q) => q.id === r.targetId);
            const reportedProfile = reportedProfiles.find((p) => p.id === r.targetId);
            const targetHref =
              r.targetType === "project"
                ? `/projects/${r.targetId}`
                : r.targetType === "question" && question
                  ? `/projects/${question.projectId}#qa`
                  : r.targetType === "profile"
                    ? `/profile/${r.targetId}`
                    : null;
            return (
              <Card key={r.id}>
                <CardHeader>
                  <CardTitle className="text-sm font-medium capitalize">
                    {r.targetType} report ·{" "}
                    {r.createdAt.toLocaleString("en-GB")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3 text-sm">
                  <p className="break-words">
                    <span className="text-muted-foreground">Reason:</span>{" "}
                    {r.reason}
                  </p>
                  <p className="text-xs text-muted-foreground break-words">
                    Target:{" "}
                    {project
                      ? `"${project.title}" (${project.status})`
                      : question
                        ? `"${question.question}"`
                        : reportedProfile
                          ? reportedProfile.fullName
                          : "already removed or not found"}
                    {targetHref && (
                      <>
                        {" · "}
                        <Link href={targetHref} className="underline">
                          view
                        </Link>
                      </>
                    )}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {r.targetType === "project" && project && project.status !== "draft" && (
                      <form action={unpublishProject}>
                        <input type="hidden" name="id" value={r.targetId} />
                        <Button type="submit" size="sm" variant="destructive">
                          Unpublish project
                        </Button>
                      </form>
                    )}
                    {r.targetType === "question" && question && (
                      <form action={removeQuestion}>
                        <input type="hidden" name="id" value={r.targetId} />
                        <Button type="submit" size="sm" variant="destructive">
                          Remove question
                        </Button>
                      </form>
                    )}
                    <form action={resolveReport}>
                      <input type="hidden" name="id" value={r.id} />
                      <input type="hidden" name="outcome" value="actioned" />
                      <Button type="submit" size="sm" variant="outline">
                        Mark actioned
                      </Button>
                    </form>
                    <form action={resolveReport}>
                      <input type="hidden" name="id" value={r.id} />
                      <input type="hidden" name="outcome" value="dismissed" />
                      <Button type="submit" size="sm" variant="ghost">
                        Dismiss
                      </Button>
                    </form>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <h2 className="mt-12 text-lg font-semibold tracking-tight">
        Contact messages {recentContact.length > 0 && `(${recentContact.length})`}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Feedback, complaints and data protection requests from /contact.
      </p>
      {recentContact.length === 0 ? (
        <p className="mt-4 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          No messages yet.
        </p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {recentContact.map((c) => (
            <Card key={c.id}>
              <CardContent className="text-sm">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium capitalize text-foreground">{c.topic}</span>
                  {" · "}
                  {c.email ?? "no email given"} · {c.createdAt.toLocaleString("en-GB")}
                </p>
                <p className="mt-2 break-words whitespace-pre-wrap">{c.message}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <h2 className="mt-12 text-lg font-semibold tracking-tight">
        Recent errors
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Unhandled server errors from the last 30 days, newest first.
      </p>
      {recentErrors.length === 0 ? (
        <p className="mt-4 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          No errors recorded.
        </p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {recentErrors.map((e) => (
            <Card key={e.id}>
              <CardHeader>
                <CardTitle className="text-sm font-medium break-words">
                  {e.message}
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                <p>
                  {e.method} {e.path} · {e.routeType}
                  {e.digest ? ` · digest ${e.digest}` : ""} ·{" "}
                  {e.createdAt.toLocaleString("en-GB")}
                </p>
                {e.stack && (
                  <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 whitespace-pre-wrap break-words">
                    {e.stack}
                  </pre>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </main>
  );
}
