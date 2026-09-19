import { cache } from "react";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import type { User } from "@supabase/supabase-js";
import { db } from "@/db";
import { profiles } from "@/db/schema";
import { createClient } from "@/lib/supabase/server";
import { classifyEmail } from "@/lib/verification";
import { REF_COOKIE, DIRECT, normalizeCode } from "@/lib/attribution";
import type { Profile } from "@/lib/profile";

// Server-only auth helpers. Never import into a client component.

// Memoised per request (React cache): the layout header, the page, and any
// server action in the same request reuse one getUser() call instead of each
// making its own network round trip to the Supabase Auth server.
export const getSessionUser = cache(async (): Promise<User | null> => {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
});

export async function requireUser(): Promise<User> {
  const user = await getSessionUser();
  if (!user) redirect("/login");
  return user;
}

// Idempotently ensure a profile row exists for an authenticated user.
// Called after sign-in/sign-up instead of a DB trigger — pure TypeScript,
// easy to reason about, and safe to call repeatedly.
export const ensureProfile = cache(async (user: User): Promise<Profile> => {
  const found = await db
    .select()
    .from(profiles)
    .where(eq(profiles.id, user.id))
    .limit(1);
  if (found.length) return found[0];

  const email = user.email ?? "";
  const cls = classifyEmail(email);
  const fullName =
    (user.user_metadata?.full_name as string | undefined)?.trim() ||
    email.split("@")[0] ||
    "New user";

  // Amendment §9: write the first-touch channel onto the record, once, at
  // profile creation. First touch already won at the cookie stage; a missing
  // code is recorded as "direct".
  const refCode =
    normalizeCode((await cookies()).get(REF_COOKIE)?.value) ?? DIRECT;

  const [created] = await db
    .insert(profiles)
    .values({
      id: user.id,
      email,
      fullName,
      isVerified: cls.isVerified,
      canSupervise: cls.canSupervise,
      refCode,
    })
    .onConflictDoNothing()
    .returning();
  if (created) return created;

  // A concurrent request already created it — fetch and return that row.
  const again = await db
    .select()
    .from(profiles)
    .where(eq(profiles.id, user.id))
    .limit(1);
  return again[0];
});

// Posting projects is restricted to verified users (a .ac.uk / .nhs.uk email,
// confirmed at signup or via the "Get verified" flow). Being verified does not
// imply supervisor status — that's chosen per project. RLS is added before
// launch; this server check is the gate. Returns user + profile so callers can
// avoid a second lookup.
export async function requirePoster(): Promise<{
  user: User;
  profile: Profile;
}> {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  if (!profile.isVerified) redirect("/projects/new");
  return { user, profile };
}

// Admin access is gated by the ADMIN_EMAILS env var (comma-separated).
// Unset = nobody; non-admins get 404 rather than a hint the page exists.
export async function requireAdmin(): Promise<{ user: User; profile: Profile }> {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const admins = (process.env.ADMIN_EMAILS ?? "")
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!admins.includes(profile.email.toLowerCase())) notFound();
  return { user, profile };
}

export async function getProfile(userId: string): Promise<Profile | null> {
  const found = await db
    .select()
    .from(profiles)
    .where(eq(profiles.id, userId))
    .limit(1);
  return found[0] ?? null;
}
