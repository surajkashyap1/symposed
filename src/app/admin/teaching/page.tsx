import { desc } from "drizzle-orm";
import { db } from "@/db";
import { teachingSubmissions, teachingTopics } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import {
  SUBMISSION_STATUS_LABELS,
  TOPIC_STATUS_LABELS,
} from "@/lib/teach-meta";
import { saveTeachingTopic, setTeachingStatus } from "@/app/admin/teaching/actions";
import { AdminNav } from "@/components/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Teaching admin | Symposed" };

const CLINICIAN_BADGE: Record<string, string> = {
  pending:
    "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
  confirmed: "border-transparent bg-success text-success-foreground",
  declined: "border-transparent bg-destructive/10 text-destructive",
};

export default async function AdminTeachingPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  await requireAdmin();
  const { error } = await searchParams;

  const [submissions, topics] = await Promise.all([
    db
      .select()
      .from(teachingSubmissions)
      .orderBy(desc(teachingSubmissions.createdAt)),
    db.select().from(teachingTopics).orderBy(teachingTopics.sortOrder),
  ]);

  const open = submissions.filter(
    (s) => !["delivered", "declined"].includes(s.status)
  );
  const closed = submissions.filter((s) =>
    ["delivered", "declined"].includes(s.status)
  );

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <AdminNav current="teaching" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">
        Teaching submissions
      </h1>
      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {open.length === 0 ? (
        <p className="mt-6 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          No open submissions.
        </p>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {open.map((s) => (
            <Card key={s.id}>
              <CardHeader>
                <CardTitle className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {s.title}
                  <Badge variant="secondary">
                    {SUBMISSION_STATUS_LABELS[s.status] ?? s.status}
                  </Badge>
                  <Badge className={CLINICIAN_BADGE[s.clinicianStatus] ?? ""}>
                    clinician {s.clinicianStatus}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 text-sm">
                <p className="text-xs text-muted-foreground">
                  {s.sessionsPlan} · {s.deliveryFormat.replaceAll("_", " ")} ·
                  audience: {s.targetAudience.join(", ")} · submitted{" "}
                  {s.createdAt.toLocaleDateString("en-GB")}
                </p>
                <p className="whitespace-pre-wrap break-words">{s.description}</p>
                <ul className="list-disc pl-5 text-xs text-muted-foreground">
                  {s.learningObjectives.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
                <p className="text-xs">
                  <span className="text-muted-foreground">Clinician:</span>{" "}
                  {s.clinicianName}, {s.clinicianGrade},{" "}
                  {s.clinicianSpecialty}, {s.clinicianInstitution} · GMC{" "}
                  {s.clinicianGmcNumber}{" "}
                  <a
                    href={`https://www.gmc-uk.org/registration-and-licensing/the-medical-register?searchQuery=${encodeURIComponent(s.clinicianGmcNumber)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline"
                  >
                    check register ↗
                  </a>
                </p>
                <p className="text-xs">
                  <a
                    href={`/admin/teaching/material/${s.id}`}
                    className="text-primary underline"
                  >
                    Download material ({s.materialsFilename})
                  </a>
                </p>

                <form action={setTeachingStatus} className="flex flex-col gap-2">
                  <input type="hidden" name="id" value={s.id} />
                  <Textarea
                    name="feedback"
                    rows={2}
                    placeholder="Feedback (required for revisions; optional otherwise)"
                    defaultValue=""
                  />
                  <div className="flex flex-wrap gap-2">
                    {s.status === "submitted" && (
                      <Button
                        type="submit"
                        name="decision"
                        value="under_review"
                        size="sm"
                        variant="outline"
                      >
                        Start review
                      </Button>
                    )}
                    <Button
                      type="submit"
                      name="decision"
                      value="revisions_requested"
                      size="sm"
                      variant="outline"
                    >
                      Request revisions
                    </Button>
                    <Button type="submit" name="decision" value="approved" size="sm">
                      Approve
                    </Button>
                    <Button
                      type="submit"
                      name="decision"
                      value="scheduled"
                      size="sm"
                      variant="outline"
                      disabled={s.clinicianStatus !== "confirmed"}
                      title={
                        s.clinicianStatus !== "confirmed"
                          ? "Blocked until the clinician confirms"
                          : undefined
                      }
                    >
                      Schedule (publish)
                    </Button>
                    <Button
                      type="submit"
                      name="decision"
                      value="declined"
                      size="sm"
                      variant="ghost"
                    >
                      Decline
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Topic editor */}
      <h2 className="mt-10 text-lg font-semibold tracking-tight">
        Commissioned topics
      </h2>
      <div className="mt-3 flex flex-col gap-3">
        {topics.map((t) => (
          <details key={t.id} className="rounded-lg border bg-card p-4">
            <summary className="cursor-pointer text-sm font-medium">
              {t.title}{" "}
              <span className="text-xs text-muted-foreground">
                ({TOPIC_STATUS_LABELS[t.status]})
              </span>
            </summary>
            <form
              action={saveTeachingTopic}
              className="mt-3 grid gap-3 sm:grid-cols-2"
            >
              <input type="hidden" name="id" value={t.id} />
              <Input name="title" defaultValue={t.title} className="sm:col-span-2" />
              <Textarea
                name="description"
                rows={3}
                defaultValue={t.description}
                className="sm:col-span-2"
              />
              <Input name="format" defaultValue={t.format} />
              <Input name="deadline" type="date" defaultValue={t.deadline ?? ""} />
              <Select
                name="status"
                defaultValue={t.status}
                options={Object.entries(TOPIC_STATUS_LABELS).map(([v, l]) => ({
                  value: v,
                  label: l,
                }))}
              />
              <Input
                name="sortOrder"
                type="number"
                defaultValue={String(t.sortOrder)}
              />
              <Button type="submit" size="sm" className="self-start">
                Save topic
              </Button>
            </form>
          </details>
        ))}
      </div>

      <details className="mt-4 rounded-lg border bg-card p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Add a new topic
        </summary>
        <form action={saveTeachingTopic} className="mt-3 grid gap-3 sm:grid-cols-2">
          <Input name="title" required placeholder="Topic title" className="sm:col-span-2" />
          <Textarea
            name="description"
            required
            rows={3}
            placeholder="What it should cover"
            className="sm:col-span-2"
          />
          <Input name="format" required placeholder="e.g. 8 sessions, 45 min, live" />
          <Input name="deadline" type="date" />
          <Select
            name="status"
            defaultValue="accepting_submissions"
            options={Object.entries(TOPIC_STATUS_LABELS).map(([v, l]) => ({
              value: v,
              label: l,
            }))}
          />
          <Input name="sortOrder" type="number" placeholder="Sort order" />
          <Button type="submit" size="sm" className="self-start">
            Add topic
          </Button>
        </form>
      </details>

      {closed.length > 0 && (
        <>
          <h2 className="mt-10 text-lg font-semibold tracking-tight">Closed</h2>
          <div className="mt-3 flex flex-col gap-2">
            {closed.map((s) => (
              <p key={s.id} className="rounded-md border bg-card px-4 py-2.5 text-sm">
                {s.title} ·{" "}
                <span className="capitalize">{SUBMISSION_STATUS_LABELS[s.status]}</span>
              </p>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
