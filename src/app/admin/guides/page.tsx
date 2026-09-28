import { desc, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders, guidePricingConfig, guideReviews } from "@/db/schema";
import { requireAdmin } from "@/lib/auth";
import { GUIDE_GRADES, formatPounds } from "@/lib/guides-meta";
import { listPendingSupportQuestions } from "@/lib/queries/member";
import { latestRunReview } from "@/lib/queries/guide-runs";
import { GuideRunPanel } from "@/components/admin/guide-run-panel";
import {
  answerSupportQuestion,
  createComplimentaryReview,
  deliverOrder,
  markOrderInProgress,
  markOrderRefunded,
  moderateGuideReview,
  updateGuidePricing,
} from "@/app/admin/guides/actions";
import { AdminNav } from "@/components/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Guides admin | Symposed" };

function workingDaysSince(from: Date, to = new Date()): number {
  let days = 0;
  const cursor = new Date(from);
  while (cursor < to) {
    cursor.setDate(cursor.getDate() + 1);
    const dow = cursor.getDay();
    if (dow !== 0 && dow !== 6) days += 1;
  }
  return days;
}

export default async function AdminGuidesPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; delivered?: string; verified?: string }>;
}) {
  await requireAdmin();
  const { error, delivered, verified } = await searchParams;

  const [orders, [config], pendingReviews, decidedReviews, [salesAgg], supportQs] =
    await Promise.all([
      db
        .select()
        .from(guideOrders)
        .where(sql`${guideOrders.status} <> 'submitted'`)
        .orderBy(desc(guideOrders.paidAt)),
      db.select().from(guidePricingConfig).limit(1),
      db
        .select()
        .from(guideReviews)
        .where(eq(guideReviews.status, "pending"))
        .orderBy(desc(guideReviews.createdAt)),
      db
        .select()
        .from(guideReviews)
        .where(sql`${guideReviews.status} <> 'pending'`)
        .orderBy(desc(guideReviews.createdAt))
        .limit(20),
      db
        .select({
          sold: sql<number>`count(*) filter (where ${guideOrders.status} in ('paid','in_progress','delivered'))::int`,
          revenuePence: sql<number>`coalesce(sum(${guideOrders.pricePaidPence}) filter (where ${guideOrders.status} in ('paid','in_progress','delivered')), 0)::int`,
          avgDeliveryDays: sql<number | null>`avg(extract(epoch from (${guideOrders.deliveredAt} - ${guideOrders.paidAt})) / 86400.0) filter (where ${guideOrders.deliveredAt} is not null)`,
        })
        .from(guideOrders),
      listPendingSupportQuestions(),
    ]);

  const active = orders.filter(
    (o) => o.status === "paid" || o.status === "in_progress"
  );
  const done = orders.filter(
    (o) => o.status === "delivered" || o.status === "refunded"
  );
  // Stage 6: the latest pipeline run for each order in the queue.
  const reviews = new Map(
    await Promise.all(
      active.map(async (o) => [o.id, await latestRunReview(o.id)] as const)
    )
  );

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <AdminNav current="guides" />
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">Guide orders</h1>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {verified && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          Decision recorded against the pipeline run.
        </div>
      )}
      {delivered && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          Delivered, the buyer has their download and review emails.
        </div>
      )}

      {/* Metrics */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        {[
          ["Guides sold", String(salesAgg.sold)],
          ["Revenue", formatPounds(salesAgg.revenuePence)],
          [
            "Avg days to delivery",
            salesAgg.avgDeliveryDays != null
              ? Number(salesAgg.avgDeliveryDays).toFixed(1)
              : "n/a",
          ],
        ].map(([label, value]) => (
          <Card key={label}>
            <CardContent>
              <p className="text-sm text-muted-foreground">{label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Active queue */}
      <h2 className="mt-10 text-lg font-semibold tracking-tight">
        Awaiting delivery {active.length > 0 && `(${active.length})`}
      </h2>
      {active.length === 0 ? (
        <p className="mt-3 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          Nothing in the queue.
        </p>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          {active.map((o) => {
            const days = o.paidAt ? workingDaysSince(o.paidAt) : 0;
            const overdue = days > 5;
            const proforma = JSON.parse(o.proforma) as Record<string, unknown>;
            return (
              <Card
                key={o.id}
                className={overdue ? "border-destructive/60" : undefined}
              >
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {o.fullName} · {o.email}
                    <Badge variant="secondary" className="capitalize">
                      {o.status.replace("_", " ")}
                    </Badge>
                    <Badge
                      className={
                        overdue
                          ? "border-transparent bg-destructive/10 text-destructive"
                          : "bg-secondary text-secondary-foreground"
                      }
                    >
                      day {days} of 7
                    </Badge>
                    {o.discountApplied && <Badge variant="outline">discounted</Badge>}
                    {o.countryMismatch && (
                      <Badge className="border-transparent bg-destructive/10 text-destructive">
                        country mismatch
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-4 text-sm">
                  <details>
                    <summary className="cursor-pointer text-xs text-muted-foreground">
                      Proforma ({String(proforma.publicationType ?? "?")} ·{" "}
                      {String(proforma.timeline ?? "?")}), expand
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-3 text-xs whitespace-pre-wrap">
                      {JSON.stringify(proforma, null, 2)}
                    </pre>
                  </details>
                  <GuideRunPanel review={reviews.get(o.id) ?? null} />
                  <p className="text-xs text-muted-foreground">
                    Paid {o.paidAt?.toLocaleString("en-GB")} ·{" "}
                    {o.pricePaidPence != null && formatPounds(o.pricePaidPence)} ·
                    countries: IP {o.ipCountry ?? "?"} / billing{" "}
                    {o.billingCountry ?? "?"} / card {o.cardCountry ?? "?"}
                  </p>

                  <form
                    action={deliverOrder}
                    className="flex flex-col gap-3 rounded-md border bg-muted/20 p-3"
                  >
                    <input type="hidden" name="id" value={o.id} />
                    <Label htmlFor={`files-${o.id}`} className="font-semibold">
                      Deliver: attach PDF + DOCX + XLSX
                    </Label>
                    <Input
                      id={`files-${o.id}`}
                      name="files"
                      type="file"
                      multiple
                      accept=".pdf,.docx,.xlsx"
                      required
                    />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Input
                        name="verifiedBy"
                        placeholder="Verified by (defaults to you)"
                      />
                      <Input
                        name="verificationNote"
                        required
                        placeholder="What you checked/changed (required)"
                      />
                    </div>
                    <Button type="submit" size="sm" className="self-start">
                      Upload & deliver
                    </Button>
                  </form>

                  <div className="flex flex-wrap gap-2">
                    {o.status === "paid" && (
                      <form action={markOrderInProgress}>
                        <input type="hidden" name="id" value={o.id} />
                        <Button type="submit" size="sm" variant="outline">
                          Mark in progress
                        </Button>
                      </form>
                    )}
                    <form action={markOrderRefunded}>
                      <input type="hidden" name="id" value={o.id} />
                      <Button type="submit" size="sm" variant="ghost">
                        Mark refunded
                      </Button>
                    </form>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Support questions (§8.8) */}
      <h2 className="mt-10 text-lg font-semibold tracking-tight">
        Support questions {supportQs.length > 0 && `(${supportQs.length} waiting)`}
      </h2>
      {supportQs.length === 0 ? (
        <p className="mt-3 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          No support questions waiting.
        </p>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {supportQs.map((q) => (
            <Card key={q.id}>
              <CardContent className="text-sm">
                <p className="text-xs text-muted-foreground">
                  {q.createdAt.toLocaleString("en-GB")}
                </p>
                <p className="mt-1 whitespace-pre-wrap break-words">{q.question}</p>
                <form action={answerSupportQuestion} className="mt-3 flex flex-col gap-2">
                  <input type="hidden" name="id" value={q.id} />
                  <Textarea name="answer" rows={3} required placeholder="Your answer" />
                  <Button type="submit" size="sm" className="self-start">
                    Send answer
                  </Button>
                </form>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pricing config */}
      <h2 className="mt-10 text-lg font-semibold tracking-tight">Pricing</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        A three-band ladder: the first free quantity of guides are free, the
        next intro quantity are the intro tier price, then the standard price.
        While payments are off, checkout is skipped and every request goes
        straight to the queue at no charge.
      </p>
      {config && (
        <form
          action={updateGuidePricing}
          className="mt-3 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-2"
        >
          <div className="grid gap-1.5">
            <Label htmlFor="freeQuantity">Free quantity (band 1)</Label>
            <Input
              id="freeQuantity"
              name="freeQuantity"
              type="number"
              min="0"
              defaultValue={String(config.freeQuantity)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="introPounds">Intro tier price (£, band 2)</Label>
            <Input
              id="introPounds"
              name="introPounds"
              type="number"
              step="0.01"
              min="0"
              defaultValue={(config.introPricePence / 100).toString()}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="introQuantity">Intro tier quantity (band 2)</Label>
            <Input
              id="introQuantity"
              name="introQuantity"
              type="number"
              min="0"
              defaultValue={String(config.introQuantity)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="standardPounds">Standard price (£, band 3)</Label>
            <Input
              id="standardPounds"
              name="standardPounds"
              type="number"
              step="0.01"
              min="1"
              defaultValue={(config.standardPricePence / 100).toString()}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="blockedCountries">
              Blocked countries (ISO codes, comma-separated)
            </Label>
            <Input
              id="blockedCountries"
              name="blockedCountries"
              defaultValue={config.blockedCountries.join(", ")}
            />
          </div>
          <label className="flex items-center gap-2.5 self-end text-sm sm:col-span-2">
            <input
              type="checkbox"
              name="paymentsEnabled"
              defaultChecked={config.paymentsEnabled}
              className="h-4 w-4 rounded border-input accent-primary"
            />
            <span>
              <span className="font-medium">Payments enabled.</span>{" "}
              <span className="text-muted-foreground">
                When off, the Stripe checkout is skipped and requests are queued
                free of charge, whatever the ladder says.
              </span>
            </span>
          </label>
          <Button type="submit" size="sm" className="self-start">
            Save pricing
          </Button>
        </form>
      )}

      {/* Review moderation */}
      <h2 className="mt-10 text-lg font-semibold tracking-tight">
        Review moderation {pendingReviews.length > 0 && `(${pendingReviews.length} pending)`}
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Approval is a spam filter, not an editorial one, never edit a
        review&apos;s substance. Complimentary reviews must carry the badge.
      </p>
      {pendingReviews.length === 0 ? (
        <p className="mt-3 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          Nothing awaiting moderation.
        </p>
      ) : (
        <div className="mt-3 flex flex-col gap-3">
          {pendingReviews.map((r) => (
            <Card key={r.id}>
              <CardContent className="text-sm">
                <p className="text-xs text-muted-foreground">
                  {r.rating}/5 · {r.reviewerName}, {r.reviewerRole}
                  {r.reviewerInstitution ? `, ${r.reviewerInstitution}` : ""}
                  {r.orderId ? " · from a paid order" : " · admin-created"}
                  {r.complimentaryGuide && " · complimentary"}
                </p>
                <p className="mt-2 whitespace-pre-wrap break-words">{r.body}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <form action={moderateGuideReview}>
                    <input type="hidden" name="id" value={r.id} />
                    <input type="hidden" name="decision" value="approve" />
                    <Button type="submit" size="sm">
                      Approve
                    </Button>
                  </form>
                  <form action={moderateGuideReview}>
                    <input type="hidden" name="id" value={r.id} />
                    <input type="hidden" name="decision" value="reject" />
                    <Button type="submit" size="sm" variant="outline">
                      Reject
                    </Button>
                  </form>
                  <form action={moderateGuideReview}>
                    <input type="hidden" name="id" value={r.id} />
                    <input type="hidden" name="decision" value="toggle_complimentary" />
                    <Button type="submit" size="sm" variant="ghost">
                      Toggle complimentary flag
                    </Button>
                  </form>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Admin-created complimentary review */}
      <details className="mt-6 rounded-lg border bg-card p-4">
        <summary className="cursor-pointer text-sm font-medium">
          Add a review from a complimentary-guide recipient
        </summary>
        <p className="mt-2 text-xs text-muted-foreground">
          Only for colleagues who genuinely received and used a guide, in their
          own words, with no steer on rating. The disclosure badge is applied
          automatically and cannot be turned off here.
        </p>
        <form
          action={createComplimentaryReview}
          className="mt-3 grid gap-3 sm:grid-cols-2"
        >
          <Input name="reviewerName" required placeholder="Reviewer name" />
          <Select
            name="reviewerRole"
            required
            placeholder="Role"
            options={GUIDE_GRADES.map((g) => ({ value: g, label: g }))}
          />
          <Input name="reviewerInstitution" placeholder="Institution (optional)" />
          <Select
            name="rating"
            required
            placeholder="Rating"
            options={[5, 4, 3, 2, 1].map((n) => ({
              value: String(n),
              label: `${n}/5`,
            }))}
          />
          <Input
            name="guideTopic"
            placeholder="Guide topic (optional)"
            className="sm:col-span-2"
          />
          <Textarea
            name="body"
            required
            rows={3}
            placeholder="The reviewer's own words, verbatim"
            className="sm:col-span-2"
          />
          <Button type="submit" size="sm" className="self-start">
            Add for moderation
          </Button>
        </form>
      </details>

      {/* History */}
      {done.length > 0 && (
        <>
          <h2 className="mt-10 text-lg font-semibold tracking-tight">History</h2>
          <div className="mt-3 flex flex-col gap-2">
            {done.map((o) => (
              <p
                key={o.id}
                className="rounded-md border bg-card px-4 py-2.5 text-sm"
              >
                <span className="font-medium">{o.fullName}</span> ·{" "}
                {o.pricePaidPence != null && formatPounds(o.pricePaidPence)} ·{" "}
                <span className="capitalize">{o.status}</span>
                {o.deliveredAt &&
                  ` · delivered ${o.deliveredAt.toLocaleDateString("en-GB")}`}
                {o.verifiedBy && ` · verified by ${o.verifiedBy}`}
              </p>
            ))}
          </div>
        </>
      )}

      {/* Recently decided reviews */}
      {decidedReviews.length > 0 && (
        <>
          <h2 className="mt-10 text-lg font-semibold tracking-tight">
            Decided reviews
          </h2>
          <div className="mt-3 flex flex-col gap-2">
            {decidedReviews.map((r) => (
              <p
                key={r.id}
                className="rounded-md border bg-card px-4 py-2.5 text-sm"
              >
                {r.rating}/5 · {r.reviewerName} ·{" "}
                <span className="capitalize">{r.status}</span>
                {r.complimentaryGuide && " · complimentary"}
              </p>
            ))}
          </div>
        </>
      )}
    </main>
  );
}
