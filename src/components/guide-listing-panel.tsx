import Link from "next/link";
import { CheckCircle2, Rocket } from "lucide-react";
import type { InferSelectModel } from "drizzle-orm";
import type { projects } from "@/db/schema";
import {
  ACKNOWLEDGEMENT_WORDING,
  AUTHOR_AI_NOTE,
  BENEFITS_AVAILABILITY_NOTE,
} from "@/lib/guides-meta";
import {
  deleteGuideDraft,
  publishGuideListing,
  regenerateGuideDraft,
  saveGuideDraft,
} from "@/app/guides/listing-actions";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type Project = InferSelectModel<typeof projects>;

// Amendment §4.4 + §8.4 — shown only inside the buyer's My guides (never on any
// public page): the manuscript disclosure blocks, then the pre-populated draft
// listing the buyer can edit and publish with one click.
export function GuideListingPanel({
  orderId,
  listing,
  offerRegenerate,
}: {
  orderId: string;
  listing: Project | null;
  offerRegenerate: boolean;
}) {
  const isDraft = listing?.status === "draft";
  const isPublished = listing != null && listing.status !== "draft";

  return (
    <div className="mt-5 flex flex-col gap-5 border-t pt-5">
      {/* §4.4 disclosure — delivered document only, never public */}
      <div className="rounded-md border bg-muted/30 p-4 text-sm leading-relaxed">
        <p className="font-semibold text-foreground">Disclosure wording</p>
        <p className="mt-2 text-muted-foreground">
          Acknowledgement to copy into your manuscript:
        </p>
        <p className="mt-1 rounded border bg-background px-3 py-2 font-medium">
          {ACKNOWLEDGEMENT_WORDING}
        </p>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          {AUTHOR_AI_NOTE}
        </p>
      </div>

      {/* §8.4 draft listing management */}
      {isPublished && (
        <div className="rounded-md border border-success/40 bg-success/5 p-4 text-sm">
          <p className="flex items-center gap-2 font-medium text-foreground">
            <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
            Your project listing is live.
          </p>
          <Link
            href={`/projects/${listing!.id}`}
            className={buttonVariants({ variant: "outline", size: "sm", className: "mt-3" })}
          >
            View your listing
          </Link>
        </div>
      )}

      {isDraft && (
        <div className="rounded-md border p-4">
          <p className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Rocket className="h-4 w-4 text-primary" aria-hidden />
            Your project listing is ready to publish
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {BENEFITS_AVAILABILITY_NOTE} Edit anything below, then publish when
            you are ready. Nothing is posted until you choose to.
          </p>

          {/* Edit form (saves, stays a draft) */}
          <form action={saveGuideDraft} className="mt-4 flex flex-col gap-3">
            <input type="hidden" name="id" value={listing!.id} />
            <div className="grid gap-1.5">
              <Label htmlFor={`title-${listing!.id}`}>Title</Label>
              <Input
                id={`title-${listing!.id}`}
                name="title"
                defaultValue={listing!.title}
                required
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`desc-${listing!.id}`}>Description</Label>
              <Textarea
                id={`desc-${listing!.id}`}
                name="description"
                rows={6}
                defaultValue={listing!.description}
                required
              />
            </div>
            <div className="grid gap-1.5 sm:max-w-[10rem]">
              <Label htmlFor={`pos-${listing!.id}`}>Positions</Label>
              <Input
                id={`pos-${listing!.id}`}
                name="positionsAvailable"
                type="number"
                min="1"
                max="50"
                defaultValue={String(listing!.positionsAvailable)}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="outline" size="sm">
                Save draft
              </Button>
            </div>
          </form>

          {/* Publish (explicit, single button) + delete */}
          <form action={publishGuideListing} className="mt-4 flex flex-col gap-3 border-t pt-4">
            <input type="hidden" name="id" value={listing!.id} />
            <label className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
              <input
                type="checkbox"
                name="noConfidentialInfo"
                className="mt-0.5 h-4 w-4 rounded border-input accent-primary"
              />
              I confirm this listing contains no confidential or patient
              information.
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" size="sm">
                Publish my listing
              </Button>
            </div>
          </form>

          <form action={deleteGuideDraft} className="mt-2">
            <input type="hidden" name="id" value={listing!.id} />
            <Button type="submit" variant="ghost" size="sm" className="text-muted-foreground">
              Delete draft
            </Button>
          </form>
        </div>
      )}

      {!listing && (
        <div className="rounded-md border border-dashed p-4 text-sm">
          {offerRegenerate ? (
            <>
              <p className="text-muted-foreground">
                Your draft listing was deleted. You can regenerate it from your
                guide rather than lose it for good.
              </p>
              <form action={regenerateGuideDraft} className="mt-3">
                <input type="hidden" name="orderId" value={orderId} />
                <Button type="submit" variant="outline" size="sm">
                  Regenerate my draft listing
                </Button>
              </form>
            </>
          ) : (
            <form action={regenerateGuideDraft}>
              <input type="hidden" name="orderId" value={orderId} />
              <p className="text-muted-foreground">
                Turn this guide into a project listing to recruit collaborators.
              </p>
              <Button type="submit" variant="outline" size="sm" className="mt-3">
                Create my draft listing
              </Button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
