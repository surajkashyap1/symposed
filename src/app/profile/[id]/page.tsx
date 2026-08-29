import Link from "next/link";
import { notFound } from "next/navigation";
import { getProfile, getSessionUser } from "@/lib/auth";
import {
  getRatingSummary,
  getReviewsForProfile,
} from "@/lib/queries/reviews";
import { getProfileCertifications, getProfileSkills } from "@/lib/queries/profiles";
import { getBadgesForProfile } from "@/lib/badges";
import { CAREER_STAGES } from "@/lib/profile";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ReportContent } from "@/components/report-content";
import { SupervisorPill, VerifiedMark } from "@/components/verified-badge";

// Tag tints per badge: informational colours, distinct from the claret used
// on buttons so a tag is never mistaken for an action.
const BADGE_TAG_CLASS: Record<string, string> = {
  new_researcher:
    "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
  research_mentor:
    "border-success/30 bg-success/10 text-success",
  project_lead:
    "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-300",
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function Stars({ value }: { value: number }) {
  const rounded = Math.round(value);
  return (
    <span aria-hidden className="text-amber-500">
      {"★".repeat(rounded)}
      <span className="text-muted-foreground/40">{"★".repeat(5 - rounded)}</span>
    </span>
  );
}

export default async function PublicProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!UUID_RE.test(id)) notFound();
  const [profile, viewer] = await Promise.all([getProfile(id), getSessionUser()]);
  if (!profile) notFound();

  const [summary, badges, reviews, skillNames, certifications] = await Promise.all([
    getRatingSummary(id),
    getBadgesForProfile(id, profile.isNewResearcher),
    getReviewsForProfile(id),
    getProfileSkills(id),
    getProfileCertifications(id),
  ]);

  const stageLabel =
    profile.careerStage === "other" && profile.careerStageOther
      ? profile.careerStageOther
      : CAREER_STAGES.find((s) => s.value === profile.careerStage)?.label ?? "Not set";
  const isSelf = viewer?.id === id;

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          {profile.avatarUrl ? (
            <img
              src={profile.avatarUrl}
              alt=""
              className="h-16 w-16 rounded-full border object-cover"
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full border bg-muted text-xl font-semibold text-muted-foreground">
              {profile.fullName.slice(0, 1).toUpperCase()}
            </div>
          )}
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              {profile.fullName}
              {profile.isVerified && <VerifiedMark className="text-xl" />}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {stageLabel}
              {profile.university ? ` · ${profile.university}` : ""}
              {profile.specialty ? ` · ${profile.specialty}` : ""}
            </p>
            {(badges.length > 0 || (profile.isVerified && profile.canSupervise)) && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {profile.isVerified && profile.canSupervise && <SupervisorPill />}
                {badges.map((b) => (
                  <Badge
                    key={b.code}
                    variant="outline"
                    title={b.description ?? undefined}
                    className={`${BADGE_TAG_CLASS[b.code] ?? ""} ${b.active ? "" : "opacity-60"}`}
                  >
                    {b.name}
                    {!b.active && " (past)"}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </div>
        {isSelf && (
          <Link
            href="/onboarding"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            Edit profile
          </Link>
        )}
      </div>

      {profile.summary && (
        <p className="mt-4 text-sm leading-relaxed">{profile.summary}</p>
      )}

      {profile.linkedinUrl && (
        <a
          href={profile.linkedinUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-sm text-primary hover:underline"
        >
          LinkedIn profile ↗
        </a>
      )}

      <section className="mt-8 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">Availability</p>
            <p className="mt-1 text-sm font-medium">
              {profile.availabilityHoursPerWeek != null
                ? `${profile.availabilityHoursPerWeek} hrs/week`
                : "Not specified"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">Skills</p>
            <p className="mt-1 text-sm font-medium">
              {skillNames.length > 0 ? skillNames.join(", ") : "Not specified"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">Looking for project types</p>
            <p className="mt-1 text-sm font-medium">
              {profile.preferredProjectTypes ?? "Not specified"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">Preferred specialties</p>
            <p className="mt-1 text-sm font-medium">
              {profile.preferredSpecialties ?? "Not specified"}
            </p>
          </CardContent>
        </Card>
      </section>

      {certifications.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold tracking-tight">Certifications</h2>
          <ul className="mt-3 flex flex-col gap-2">
            {certifications.map((certification) => (
              <li
                key={certification.id}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
              >
                <span className="font-medium">{certification.name}</span>
                {certification.proofUrl && (
                  <a
                    href={certification.proofUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    View proof
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Ratings */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">As a team member</p>
            {summary.memberAvg != null ? (
              <p className="mt-1 flex items-center gap-2 text-lg font-semibold">
                {summary.memberAvg.toFixed(1)} <Stars value={summary.memberAvg} />
                <span className="text-sm font-normal text-muted-foreground">
                  ({summary.memberCount})
                </span>
              </p>
            ) : (
              <p className="mt-1 text-sm text-muted-foreground">No reviews yet</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <p className="text-sm text-muted-foreground">As a supervisor</p>
            {summary.supervisorAvg != null ? (
              <p className="mt-1 flex items-center gap-2 text-lg font-semibold">
                {summary.supervisorAvg.toFixed(1)}{" "}
                <Stars value={summary.supervisorAvg} />
                <span className="text-sm font-normal text-muted-foreground">
                  ({summary.supervisorCount})
                </span>
              </p>
            ) : (
              <p className="mt-1 text-sm text-muted-foreground">No reviews yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Reviews */}
      <section className="mt-10">
        <h2 className="text-lg font-semibold tracking-tight">
          Reviews {reviews.length > 0 && `(${reviews.length})`}
        </h2>
        {reviews.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">No reviews yet.</p>
        ) : (
          <ul className="mt-4 flex flex-col gap-4">
            {reviews.map((r) => (
              <li key={r.id} className="rounded-lg border p-4">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    {Number(r.ratingOverall).toFixed(1)}{" "}
                    <Stars value={Number(r.ratingOverall)} />
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {r.createdAt.toLocaleDateString("en-GB")}
                  </span>
                </div>
                {r.comment && <p className="mt-2 text-sm">{r.comment}</p>}
                <p className="mt-2 text-xs text-muted-foreground">
                  {r.direction === "supervisor_to_member"
                    ? "From a supervisor"
                    : "From a team member"}
                  {r.reviewerName ? ` · ${r.reviewerName}` : " · anonymous"}
                  {r.projectTitle ? ` · ${r.projectTitle}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {viewer && viewer.id !== profile.id && (
        <div className="mt-10">
          <ReportContent
            targetType="profile"
            targetId={profile.id}
            backTo={`/profile/${profile.id}`}
            label="Report this profile"
          />
        </div>
      )}
    </main>
  );
}
