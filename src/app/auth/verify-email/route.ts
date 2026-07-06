import { type NextRequest, NextResponse } from "next/server";
import { and, eq, gt, isNull, or } from "drizzle-orm";
import { db } from "@/db";
import { profiles, verifications } from "@/db/schema";

// Confirms the links we email for both verification kinds: a valid, unexpired,
// pending token either proves the login email works (login_email) or flips the
// profile to verified (.ac.uk / .nhs.uk academic check). Verification grants
// posting rights only — supervisor status is chosen per project, not implied.
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const token = searchParams.get("token");

  if (token) {
    const [row] = await db
      .select({
        id: verifications.id,
        profileId: verifications.profileId,
        type: verifications.type,
      })
      .from(verifications)
      .where(
        and(
          eq(verifications.token, token),
          eq(verifications.status, "pending"),
          or(isNull(verifications.expiresAt), gt(verifications.expiresAt, new Date()))
        )
      )
      .limit(1);

    if (row) {
      const now = new Date();
      await db
        .update(verifications)
        .set({ status: "verified", verifiedAt: now, token: null })
        .where(eq(verifications.id, row.id));
      await db
        .update(profiles)
        .set(
          row.type === "login_email"
            ? { emailConfirmedAt: now, updatedAt: now }
            : { isVerified: true, updatedAt: now }
        )
        .where(eq(profiles.id, row.profileId));

      return NextResponse.redirect(
        new URL(
          row.type === "login_email" ? "/dashboard?confirmed=1" : "/dashboard?verified=1",
          origin
        )
      );
    }
  }

  return NextResponse.redirect(
    new URL("/onboarding?verify=invalid#verify", origin)
  );
}
