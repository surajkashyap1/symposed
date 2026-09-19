import Link from "next/link";
import { Plus } from "lucide-react";
import { requireUser, ensureProfile } from "@/lib/auth";
import { CAREER_STAGES } from "@/lib/profile";
import { getProjectsByOwner } from "@/lib/queries/projects";
import { getProfileCertifications, getProfileSkills } from "@/lib/queries/profiles";
import { getApplicationAllowance } from "@/lib/queries/applications";
import { TIER_LABEL } from "@/lib/queries/entitlements";
import { getProjectRecord, getSupportState } from "@/lib/queries/member";
import { resendEmailConfirmation } from "@/app/auth/actions";
import { askSupportQuestion } from "@/app/dashboard/actions";
import { ProjectCard } from "@/components/project-card";
import { VerifiedPill } from "@/components/verified-badge";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ confirmation?: string; support?: string }>;
}) {
  const user = await requireUser();
  const profile = await ensureProfile(user);
  const { confirmation, support } = await searchParams;
  // Only nag about confirmation when we can actually send the email.
  const emailProviderConfigured = Boolean(
    process.env.RESEND_API_KEY && process.env.RESEND_FROM
  );
  const [myProjects, skillNames, certifications, allowance, record, supportState] =
    await Promise.all([
      getProjectsByOwner(user.id),
      getProfileSkills(user.id),
      getProfileCertifications(user.id),
      getApplicationAllowance(user.id),
      getProjectRecord(user.id),
      getSupportState(user.id),
    ]);

  const stageLabel =
    CAREER_STAGES.find((s) => s.value === profile.careerStage)?.label ?? "Not set";

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-12">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {profile.avatarUrl ? (
            <img
              src={profile.avatarUrl}
              alt=""
              className="h-14 w-14 rounded-full border object-cover"
            />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full border bg-muted text-lg font-semibold text-muted-foreground">
              {profile.fullName.slice(0, 1).toUpperCase()}
            </div>
          )}
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Hi, {profile.fullName}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{profile.email}</p>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Link
            href={`/profile/${user.id}`}
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            Public profile
          </Link>
          <Link href="/onboarding" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Edit profile
          </Link>
        </div>
      </div>

      {emailProviderConfigured && !profile.emailConfirmedAt && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          {confirmation === "sent" ? (
            <p>Confirmation email sent, check your inbox (and spam folder).</p>
          ) : (
            <>
              <p>
                Please confirm your email address so listers and applicants can
                reach you. We sent a link to {profile.email}.
              </p>
              <form action={resendEmailConfirmation}>
                <Button type="submit" variant="outline" size="sm">
                  Resend email
                </Button>
              </form>
            </>
          )}
        </div>
      )}

      {/* Verification + status badges */}
      <div className="mt-6 flex flex-wrap gap-2">
        {profile.isVerified ? (
          <VerifiedPill />
        ) : (
          <Badge variant="secondary">
            Unverified. Verify with a university or health-service email.
          </Badge>
        )}
        {profile.isNewResearcher && (
          <Badge
            variant="outline"
            className="border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
          >
            New researcher
          </Badge>
        )}
      </div>

      {/* Profile completeness */}
      <Card className="mt-8">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Profile completeness</CardTitle>
            <span className="text-sm font-medium text-muted-foreground">
              {profile.profileCompleteness}%
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${profile.profileCompleteness}%` }}
            />
          </div>
          <dl className="mt-6 grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
            <div>
              <dt className="text-muted-foreground">Career stage</dt>
              <dd className="mt-0.5 font-medium">{stageLabel}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">University</dt>
              <dd className="mt-0.5 font-medium">{profile.university ?? "Not set"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Specialty</dt>
              <dd className="mt-0.5 font-medium">{profile.specialty ?? "Not set"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Availability</dt>
              <dd className="mt-0.5 font-medium">
                {profile.availabilityHoursPerWeek != null
                  ? `${profile.availabilityHoursPerWeek} hrs/week`
                  : "Not set"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Looking for</dt>
              <dd className="mt-0.5 font-medium">
                {profile.preferredProjectTypes ?? "Not set"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Preferred specialties</dt>
              <dd className="mt-0.5 font-medium">
                {profile.preferredSpecialties ?? "Not set"}
              </dd>
            </div>
          </dl>
          <div className="mt-6 grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <p className="text-muted-foreground">Skills</p>
              <p className="mt-0.5 font-medium">
                {skillNames.length > 0 ? skillNames.join(", ") : "Not set"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Certifications</p>
              <p className="mt-0.5 font-medium">
                {certifications.length > 0
                  ? certifications.map((certification) => certification.name).join(", ")
                  : "Not set"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Membership, credits and track record (§8.3 / §8.9) */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Membership and credits</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              <Badge variant="outline">{TIER_LABEL[allowance.tier]}</Badge>
            </p>
            <p className="mt-3">
              <span className="text-2xl font-semibold tabular-nums">
                {allowance.remaining}
              </span>{" "}
              <span className="text-muted-foreground">
                of {allowance.limit} applications left this week
              </span>
            </p>
            {allowance.remaining === 0 && allowance.resetsAt && (
              <p className="mt-1 text-xs text-muted-foreground">
                Resets {allowance.resetsAt.toLocaleDateString("en-GB")}.
              </p>
            )}
            {allowance.tier === "standard" && (
              <p className="mt-3 text-xs text-muted-foreground">
                Post a project to move up to 6 per week, or list the project
                from a Symposed guide for 9.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Your track record</CardTitle>
              <Link
                href="/profile/record"
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Export
              </Link>
            </div>
          </CardHeader>
          <CardContent className="text-sm">
            <dl className="grid grid-cols-3 gap-2 text-center">
              <div>
                <dt className="text-xs text-muted-foreground">Led</dt>
                <dd className="text-2xl font-semibold tabular-nums">
                  {record.led.length}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Recruited</dt>
                <dd className="text-2xl font-semibold tabular-nums">
                  {record.collaboratorsRecruited}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Joined</dt>
                <dd className="text-2xl font-semibold tabular-nums">
                  {record.joined.length}
                </dd>
              </div>
            </dl>
            <p className="mt-3 text-xs text-muted-foreground">
              We confirm what happened, and nothing more.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Direct support (§8.8) */}
      <Card className="mt-4">
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-base">Direct support</CardTitle>
            {supportState.eligible && (
              <span className="text-sm text-muted-foreground">
                {supportState.remaining} of {supportState.allowance} questions left
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="text-sm">
          {support === "asked" && (
            <p className="mb-3 rounded-md border border-success/30 bg-success/10 px-3 py-2">
              Question received. We usually reply within {supportState.responseDays}{" "}
              working days.
            </p>
          )}
          {support && support !== "asked" && (
            <p className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              {support}
            </p>
          )}
          {!supportState.eligible ? (
            <p className="text-muted-foreground">
              Ask us about your methodology, screening decisions or analysis.
              This becomes available once you have a live project listing.
            </p>
          ) : supportState.remaining > 0 ? (
            <form action={askSupportQuestion} className="flex flex-col gap-2">
              <Textarea
                name="question"
                rows={3}
                required
                placeholder="Ask about your methodology, screening decisions or analysis."
              />
              <p className="text-xs text-muted-foreground">
                We usually reply within {supportState.responseDays} working days.
              </p>
              <SubmitButton size="sm" className="self-start" pendingLabel="Sending...">
                Ask a question
              </SubmitButton>
            </form>
          ) : (
            <p className="text-muted-foreground">
              You have used your {supportState.allowance} support questions. Get
              in touch if you need more.
            </p>
          )}

          {supportState.questions.length > 0 && (
            <ul className="mt-4 flex flex-col gap-3 border-t pt-4">
              {supportState.questions.map((q) => (
                <li key={q.id}>
                  <p className="font-medium">{q.question}</p>
                  {q.answer ? (
                    <p className="mt-1 text-muted-foreground">{q.answer}</p>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Awaiting a reply.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* My projects */}
      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">My projects</h2>
          <div className="flex gap-2">
            <Link
              href="/projects"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              Browse all
            </Link>
            {profile.isVerified && (
              <Link
                href="/projects/new"
                className={buttonVariants({ size: "sm", className: "gap-1.5" })}
              >
                <Plus className="h-4 w-4" aria-hidden />
                Post a project
              </Link>
            )}
          </div>
        </div>

        {myProjects.length === 0 ? (
          <p className="mt-4 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {profile.isVerified
              ? "You haven’t posted any projects yet."
              : "Browse open opportunities to find your first project."}
          </p>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {myProjects.map((p) => (
              <ProjectCard key={p.id} p={p} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
