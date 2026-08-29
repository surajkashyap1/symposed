import Link from "next/link";
import { notFound } from "next/navigation";
import { getSessionUser } from "@/lib/auth";
import { getLiveListing } from "@/lib/queries/availability";
import { listingDisplayName, CONTACT_MAX_CHARS } from "@/lib/board-meta";
import { CAREER_STAGES } from "@/lib/profile";
import { sendListingContact } from "@/app/available/actions";
import { isUuid } from "@/lib/utils";
import { ReportContent } from "@/components/report-content";
import { Button, buttonVariants } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Get in touch — Symposed" };

export default async function ListingContactPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string; sent?: string; reported?: string }>;
}) {
  const [{ id }, { error, sent, reported }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (!isUuid(id)) notFound();

  const [listing, user] = await Promise.all([
    getLiveListing(id),
    getSessionUser(),
  ]);
  if (!listing) notFound();

  const name = listingDisplayName(
    listing.ownerName ?? "Anonymous",
    listing.displayInitialsOnly
  );
  const stage = CAREER_STAGES.find(
    (s) => s.value === listing.ownerCareerStage
  )?.label;

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Link
        href="/available"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← All available people
      </Link>

      {reported && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          Thanks — your report has been received and will be reviewed.
        </div>
      )}

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Get in touch with {name}</CardTitle>
          <CardDescription>
            {[stage, listing.showInstitution ? listing.ownerUniversity : null]
              .filter(Boolean)
              .join(" · ") || "Available for projects"}
            {" — "}
            &ldquo;{listing.headline}&rdquo;
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sent ? (
            <div className="flex flex-col gap-4">
              <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
                Message sent. {name} has been notified and can reply straight
                to you by email.
              </p>
              <Link href="/available" className={buttonVariants({ variant: "outline" })}>
                Back to the board
              </Link>
            </div>
          ) : !user ? (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-muted-foreground">
                You need to be signed in to send a message, so {name} can see
                who&apos;s contacting them.
              </p>
              <Link href="/login" className={buttonVariants()}>
                Log in to get in touch
              </Link>
            </div>
          ) : (
            <form action={sendListingContact} className="flex flex-col gap-4">
              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}
              <input type="hidden" name="listingId" value={listing.id} />
              <div className="grid gap-2">
                <Label htmlFor="body">Your message</Label>
                <Textarea
                  id="body"
                  name="body"
                  required
                  rows={6}
                  maxLength={CONTACT_MAX_CHARS}
                  placeholder="Introduce your project: what it is, the expected output, the time commitment, and why this person is a good fit."
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Your name, role and a link to your Symposed profile are included
                automatically, and replies go straight to your email address.
              </p>
              <Button type="submit" className="self-start">
                Send message
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      {user && (
        <div className="mt-8">
          <ReportContent
            targetType="availability_listing"
            targetId={listing.id}
            backTo={`/available/${listing.id}/contact`}
            label="Report this listing"
          />
        </div>
      )}
    </main>
  );
}
