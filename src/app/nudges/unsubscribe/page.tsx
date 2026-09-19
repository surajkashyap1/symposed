import Link from "next/link";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { profiles } from "@/db/schema";
import { verifyNudgeUnsubscribe } from "@/lib/nudge-token";
import { isUuid } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

export const metadata = { title: "Unsubscribed | Symposed" };

// Amendment §8.5 — one-click unsubscribe for the listing-nudge emails only.
// Works without login via a signed link; transactional email is unaffected.
export default async function NudgeUnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<{ u?: string; sig?: string }>;
}) {
  const { u, sig } = await searchParams;
  const ok = !!u && !!sig && isUuid(u) && verifyNudgeUnsubscribe(u, sig);

  if (ok) {
    await db
      .update(profiles)
      .set({ listingNudgeOptOut: true, updatedAt: new Date() })
      .where(eq(profiles.id, u));
  }

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-6 py-16 text-center">
      <h1 className="font-heading text-2xl font-semibold tracking-tight">
        {ok ? "You are unsubscribed" : "Link not valid"}
      </h1>
      <p className="mt-3 text-sm text-muted-foreground">
        {ok
          ? "You will no longer receive nudges about publishing your project listing. Your transactional and account emails are unaffected."
          : "We could not verify this unsubscribe link. It may have expired."}
      </p>
      <Link href="/" className={buttonVariants({ variant: "outline", className: "mt-6" })}>
        Back to Symposed
      </Link>
    </main>
  );
}
