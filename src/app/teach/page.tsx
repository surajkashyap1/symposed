import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { joinTeachingWaitlist } from "@/app/teach/actions";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SubmitButton } from "@/components/submit-button";

export const metadata = {
  title: "Teach on Symposed",
  description:
    "Symposed will soon host teaching content created by students and doctors. Leave your email and we will tell you when it opens.",
};

export default async function TeachPage({
  searchParams,
}: {
  searchParams: Promise<{ joined?: string; error?: string }>;
}) {
  const [user, { joined, error }] = await Promise.all([
    getSessionUser(),
    searchParams,
  ]);

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-14">
      <h1 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
        Teach through Symposed
      </h1>

      {/* Amendment §10 — short description + in-development statement, verbatim */}
      <p className="mt-5 text-lg leading-relaxed text-muted-foreground">
        Symposed will soon host teaching content created by students and
        doctors. You will be able to design and deliver a course, reach an
        audience across the UK, and receive structured feedback and a record of
        what you taught.
      </p>
      <p className="mt-4 text-lg leading-relaxed text-muted-foreground">
        This feature is in development. Leave your email and we will tell you
        when it opens.
      </p>

      {/* Single email capture */}
      <div className="mt-8 rounded-lg border bg-card p-6">
        {joined ? (
          <p className="flex items-center gap-2 text-sm font-medium text-success">
            <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden />
            Thanks. We will email you when teaching opens.
          </p>
        ) : (
          <form action={joinTeachingWaitlist} className="flex flex-col gap-3">
            <Label htmlFor="email">Tell me when teaching opens</Label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                id="email"
                name="email"
                type="email"
                required
                placeholder="you@example.com"
                defaultValue={user?.email ?? ""}
                className="sm:max-w-xs"
              />
              <SubmitButton pendingLabel="Saving...">Notify me</SubmitButton>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        )}
      </div>

      {/* Portfolio disclaimer — from the main specification, unchanged. It
          applies as soon as any portfolio benefit is mentioned at all. */}
      <div className="mt-10 rounded-lg border-2 border-amber-300 bg-amber-50 p-6 text-sm leading-relaxed text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
        <p className="flex items-center gap-2 font-semibold">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
          Important: you are responsible for checking what your specialty
          actually requires.
        </p>
        <p className="mt-3">
          Person specifications differ substantially between specialties and
          change every recruitment cycle. Some specialties score a
          self-assessment at application, some grade a portfolio only at
          interview, and some select on the MSRA with no portfolio score at
          all. Some require teaching to have been delivered live rather than as
          pre-recorded material.
        </p>
        <p className="mt-3">
          Symposed provides accurate evidence of the teaching you actually
          delivered. How that evidence scores, and whether it counts at all, is
          determined entirely by your specialty&apos;s published criteria, which
          you must check yourself before making any claim. We make no guarantee
          about points.
        </p>
        <p className="mt-3">
          You must be able to evidence every claim you make in a training
          application, and applications are subject to audit. Symposed will
          confirm what happened and nothing more.
        </p>
      </div>
    </main>
  );
}
