import { redirect } from "next/navigation";
import { and, eq, gt } from "drizzle-orm";
import { db } from "@/db";
import { verifications } from "@/db/schema";
import { requireUser, ensureProfile } from "@/lib/auth";
import { confirmSignupOtp, resendSignupOtp } from "@/app/auth/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Confirm your email — Symposed" };

export default async function SignupConfirmPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; resent?: string }>;
}) {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  if (profile.emailConfirmedAt) redirect("/onboarding");
  const { error, resent } = await searchParams;

  // Manual fallback while no email provider is configured: surface the code
  // inline so signup is never blocked by missing infrastructure. Goes away
  // the moment Resend env vars exist.
  const emailConfigured = Boolean(
    process.env.RESEND_API_KEY && process.env.RESEND_FROM
  );
  let manualCode: string | null = null;
  if (!emailConfigured) {
    const [pending] = await db
      .select({ code: verifications.token })
      .from(verifications)
      .where(
        and(
          eq(verifications.profileId, user.id),
          eq(verifications.type, "login_email"),
          eq(verifications.status, "pending"),
          gt(verifications.expiresAt, new Date())
        )
      )
      .limit(1);
    manualCode = pending?.code ?? null;
  }

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Check your email</CardTitle>
          <CardDescription>
            We&apos;ve sent a 6-digit code to{" "}
            <strong>{profile.email}</strong>. Enter it below to finish creating
            your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {resent && (
            <p className="rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
              A new code is on its way — check your inbox (and spam folder).
            </p>
          )}
          {error && (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </p>
          )}
          {manualCode && (
            <p className="rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground">
              Email isn&apos;t configured yet, so here&apos;s your code
              directly: <strong className="tabular-nums">{manualCode}</strong>
            </p>
          )}

          <form action={confirmSignupOtp} className="flex flex-col gap-3">
            <div className="grid gap-2">
              <Label htmlFor="code">Confirmation code</Label>
              <Input
                id="code"
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="\d{6}"
                maxLength={6}
                required
                placeholder="123456"
                className="text-center text-lg tracking-[0.4em] tabular-nums"
              />
            </div>
            <Button type="submit">Confirm email</Button>
          </form>

          <form action={resendSignupOtp} className="text-center">
            <button
              type="submit"
              className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Didn&apos;t get it? Send a new code
            </button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
