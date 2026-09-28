import { verifyGuideRun } from "@/app/admin/guides/actions";
import type { RunReview } from "@/lib/queries/guide-runs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const PROSPERO_SEARCH = "https://www.crd.york.ac.uk/PROSPERO/";

const OUTCOME_STYLE: Record<string, string> = {
  pass: "bg-secondary text-secondary-foreground",
  flag: "border-transparent bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-100",
  downgrade: "border-transparent bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-100",
  reject: "border-transparent bg-destructive/10 text-destructive",
};

function fmt(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return Number.isInteger(value) ? value.toLocaleString("en-GB") : value.toFixed(2);
}

// Stage 6 (build spec §4): one screen per order for the human reviewer, with
// everything needed to approve, edit or reject the pipeline's proposal.
export function GuideRunPanel({ review }: { review: RunReview | null }) {
  if (!review) {
    return (
      <p className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">
        No pipeline run yet. It is picked up by the next Friday batch.
      </p>
    );
  }
  const { run, gates, prospero, tieBreak, searches, statusCounts, verifications } = review;
  const decided = verifications[0];
  const metrics = (run.metrics ?? {}) as Record<string, unknown>;
  const recentReviews = review.winner?.recentReviews;
  const eligible = review.winner?.eligibleStudies;
  const screenedPlausible =
    (statusCounts["likely eligible"] ?? 0) + (statusCounts["unclear, check full text"] ?? 0);

  return (
    <div className="flex flex-col gap-3 rounded-md border bg-muted/10 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">Pipeline draft</span>
        <Badge variant="secondary">{run.status.replace("_", " ")}</Badge>
        {run.costUsd != null && (
          <span className="text-xs text-muted-foreground">
            cost ${Number(run.costUsd).toFixed(2)}
          </span>
        )}
        {decided && (
          <Badge variant="outline">
            {decided.action.replaceAll("_", " ")} by {decided.reviewer}
          </Badge>
        )}
      </div>

      {run.status === "running" && (
        <p className="text-xs text-muted-foreground">Running since {run.startedAt.toLocaleString("en-GB")}.</p>
      )}
      {run.status === "failed" && (
        <p className="text-xs text-destructive">Failed: {review.error || "unknown error"}. It is retried in the next batch.</p>
      )}
      {run.status === "needs_contact" && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          Nothing fits the stated requirements. Email the user before going further:{" "}
          {run.contactReason}
        </div>
      )}

      {run.status === "found" && (
        <>
          <div>
            <p className="text-base font-medium leading-snug">{run.title}</p>
            <p className="text-xs text-muted-foreground">
              {run.publicationType} · axis: {run.axis}
            </p>
            {review.rationale && (
              <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{review.rationale}</p>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <div><dt className="text-muted-foreground">Recent systematic reviews</dt><dd className="font-medium">{fmt(recentReviews)}</dd></div>
            <div><dt className="text-muted-foreground">Eligible (count / screened)</dt><dd className="font-medium">{fmt(eligible)} / {screenedPlausible}</dd></div>
            <div><dt className="text-muted-foreground">Candidates tried</dt><dd className="font-medium">{fmt(metrics.candidates_generated as number)}</dd></div>
            <div><dt className="text-muted-foreground">Tied</dt><dd className="font-medium">{fmt(metrics.tied_candidates as number)}</dd></div>
          </dl>

          {review.warnings.length > 0 && (
            <ul className="list-disc rounded-md border border-amber-300 bg-amber-50 py-2 pl-7 pr-3 text-xs text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
              {review.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}

          <details open>
            <summary className="cursor-pointer text-xs font-medium">Gates</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {gates.map((g) => (
                <Badge key={g.name} className={OUTCOME_STYLE[g.outcome] ?? ""} title={g.detail}>
                  {g.name.replaceAll("_", " ")}: {g.outcome} ({fmt(g.value)} vs {fmt(g.threshold)})
                </Badge>
              ))}
            </div>
          </details>

          <details>
            <summary className="cursor-pointer text-xs font-medium">
              Most similar existing work ({review.similar.length})
            </summary>
            <ul className="mt-2 flex flex-col gap-1 text-xs">
              {review.similar.map((s) => (
                <li key={s.url}>
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-primary underline">
                    {s.title}
                  </a>{" "}
                  <span className="text-muted-foreground">(similarity {s.score.toFixed(2)})</span>
                </li>
              ))}
            </ul>
          </details>

          {prospero && (
            <details>
              <summary className="cursor-pointer text-xs font-medium">
                PROSPERO: {prospero.verdict} (mirror current to {prospero.mirrorCoveredTo})
              </summary>
              <ul className="mt-2 flex flex-col gap-1 text-xs">
                {(prospero.matches as { registration_id: string; title: string; score: number; url: string }[]).map((m) => (
                  <li key={m.registration_id}>
                    <a href={m.url} target="_blank" rel="noreferrer" className="text-primary underline">
                      {m.registration_id}
                    </a>{" "}
                    {m.title} <span className="text-muted-foreground">({m.score.toFixed(2)})</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs">
                Live check: search{" "}
                <a href={PROSPERO_SEARCH} target="_blank" rel="noreferrer" className="text-primary underline">
                  PROSPERO
                </a>{" "}
                for <span className="font-medium">{prospero.searchTerms}</span>, then record the date below.
              </p>
            </details>
          )}

          {tieBreak && (
            <details>
              <summary className="cursor-pointer text-xs font-medium">Tie break (model judgement)</summary>
              <p className="mt-2 whitespace-pre-wrap text-xs">{tieBreak.summary}</p>
              <ol className="mt-2 list-decimal pl-5 text-xs">
                {(tieBreak.candidates as string[]).map((t, i) => (
                  <li key={t} className={i === tieBreak.modelChoice ? "font-medium" : ""}>
                    {t} {i === tieBreak.modelChoice && "(chosen)"}
                  </li>
                ))}
              </ol>
            </details>
          )}

          <details>
            <summary className="cursor-pointer text-xs font-medium">Search appendix ({searches.length})</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <tbody>
                  {searches.map((s) => (
                    <tr key={s.id} className="border-t align-top">
                      <td className="py-1 pr-2 text-muted-foreground">{s.source}</td>
                      <td className="py-1 pr-2 font-mono break-all">{s.query}</td>
                      <td className="py-1 text-right">{fmt(s.resultCount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          {run.hasDocx && (
            <a href={`/admin/guides/runs/${run.id}/docx`} className="text-xs text-primary underline">
              Download the draft guide (.docx)
            </a>
          )}
        </>
      )}

      {(run.status === "found" || run.status === "needs_contact") && !decided && (
        <form action={verifyGuideRun} className="flex flex-col gap-2 border-t pt-3">
          <input type="hidden" name="runId" value={run.id} />
          <Label htmlFor={`action-${run.id}`} className="text-xs font-semibold">Your decision</Label>
          <Select
            id={`action-${run.id}`}
            name="action"
            required
            placeholder="Choose"
            options={[
              { value: "approved", label: "Approve" },
              { value: "edited_and_approved", label: "Edit and approve" },
              { value: "rejected", label: "Reject and re-run" },
            ]}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <Input name="editedTitle" placeholder="Edited title (edit and approve)" />
            <Input name="liveProsperoCheckedOn" type="date" aria-label="Live PROSPERO check date" />
          </div>
          {tieBreak && (
            <Select
              name="overrideChoice"
              placeholder="Tie break override (optional)"
              options={(tieBreak.candidates as string[]).map((t, i) => ({
                value: String(i),
                label: `Prefer: ${t}`,
              }))}
            />
          )}
          <Textarea name="notes" rows={2} placeholder="What you changed, or why you rejected it" />
          <Input name="reviewer" placeholder="Reviewer (defaults to you)" />
          <Button type="submit" size="sm" className="self-start">Record decision</Button>
        </form>
      )}
    </div>
  );
}
