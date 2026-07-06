import { notFound } from "next/navigation";
import { desc } from "drizzle-orm";
import { db } from "@/db";
import { appErrors } from "@/db/schema";
import { requireUser, ensureProfile } from "@/lib/auth";
import { getMetrics } from "@/lib/queries/metrics";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Admin-only metrics. Access is gated by the ADMIN_EMAILS env var (comma-
// separated). If unset, nobody can view it — returns 404 rather than leaking
// that the page exists.
export default async function AdminPage() {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const admins = (process.env.ADMIN_EMAILS ?? "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!admins.includes(profile.email.toLowerCase())) notFound();

  const [m, recentErrors] = await Promise.all([
    getMetrics(),
    db.select().from(appErrors).orderBy(desc(appErrors.createdAt)).limit(25),
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
      <h1 className="text-2xl font-semibold tracking-tight">Metrics</h1>
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
