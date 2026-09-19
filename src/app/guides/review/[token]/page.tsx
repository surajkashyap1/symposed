import { notFound } from "next/navigation";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { guideReviews } from "@/db/schema";
import { getOrderByReviewToken } from "@/lib/queries/guides";
import { GUIDE_GRADES } from "@/lib/guides-meta";
import { submitGuideReview, requestGuideReviewRemoval } from "@/app/guides/review-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Review your guide | Symposed" };

// Single-use review link from the delivery email (spec §3.5): no login —
// the token identifies the buyer.
export default async function GuideReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ error?: string; done?: string; removed?: string }>;
}) {
  const [{ token }, { error, done, removed }] = await Promise.all([
    params,
    searchParams,
  ]);
  const order = await getOrderByReviewToken(token);
  if (!order || order.status !== "delivered") notFound();

  const [existing] = await db
    .select()
    .from(guideReviews)
    .where(eq(guideReviews.orderId, order.id))
    .limit(1);

  return (
    <main className="mx-auto w-full max-w-xl flex-1 px-6 py-12">
      <Card>
        <CardHeader>
          <CardTitle>How was your guide?</CardTitle>
          <CardDescription>
            Honest words only, we publish reviews as written, after a spam
            check. You can request removal of your review at any time from
            this same link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {removed ? (
            <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
              Your review has been removed. Thanks for letting us know.
            </p>
          ) : existing ? (
            <div className="flex flex-col gap-4">
              <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
                {done
                  ? "Thank you, your review has been submitted and will appear once it clears a quick spam check."
                  : "You've already reviewed this guide."}
              </p>
              <form action={requestGuideReviewRemoval}>
                <input type="hidden" name="token" value={token} />
                <Button type="submit" variant="outline" size="sm">
                  Remove my review
                </Button>
              </form>
            </div>
          ) : (
            <form action={submitGuideReview} className="flex flex-col gap-5">
              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}
              <input type="hidden" name="token" value={token} />

              <div className="grid gap-2">
                <Label htmlFor="rating">Rating</Label>
                <Select
                  id="rating"
                  name="rating"
                  required
                  placeholder="Out of 5"
                  options={[5, 4, 3, 2, 1].map((n) => ({
                    value: String(n),
                    label: `${n}, ${["", "poor", "fair", "good", "very good", "excellent"][n]}`,
                  }))}
                />
              </div>

              <div className="grid gap-2">
                <Label htmlFor="body">Your review</Label>
                <Textarea
                  id="body"
                  name="body"
                  required
                  rows={5}
                  minLength={40}
                  placeholder="What you bought it for, what you got, and whether it moved your project forward. At least 40 characters."
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="grid gap-2">
                  <Label htmlFor="displayName">Display name</Label>
                  <Input
                    id="displayName"
                    name="displayName"
                    required
                    defaultValue={order.fullName}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="reviewerRole">Your grade or role</Label>
                  <Select
                    id="reviewerRole"
                    name="reviewerRole"
                    required
                    placeholder="Choose"
                    options={GUIDE_GRADES.map((g) => ({ value: g, label: g }))}
                  />
                </div>
              </div>

              <div className="grid gap-2">
                <Label htmlFor="guideTopic">
                  Guide topic (optional, shown with your review)
                </Label>
                <Input
                  id="guideTopic"
                  name="guideTopic"
                  placeholder="e.g. Systematic review in emergency medicine"
                />
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="showInstitution"
                  className="h-4 w-4 rounded border-input accent-primary"
                />
                Show my institution with the review
              </label>
              {/* Institution captured only if opted in */}
              <div className="grid gap-2">
                <Label htmlFor="institution">Institution (optional)</Label>
                <Input id="institution" name="institution" />
              </div>

              <Button type="submit" className="self-start">
                Submit review
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
