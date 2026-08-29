import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Briefcase,
  CalendarDays,
  GraduationCap,
  Stethoscope,
  UserPlus,
  Users,
} from "lucide-react";
import type { ComponentType, ReactNode, SVGProps } from "react";
import { getSessionUser } from "@/lib/auth";
import { getProjectById } from "@/lib/queries/projects";
import {
  getApplicationAllowance,
  getMyApplication,
} from "@/lib/queries/applications";
import { getQuestionsForProject } from "@/lib/queries/questions";
import { closeProject, reopenProject, completeProject } from "@/app/projects/actions";
import { projectTypeLabel, experienceLabel } from "@/lib/project-meta";
import { STATUS_LABELS, STATUS_BADGE_CLASS } from "@/lib/application-meta";
import { CAREER_STAGES } from "@/lib/profile";
import { formatDateUK } from "@/lib/utils";
import { ApplicationForm } from "@/components/application-form";
import { ListingQA } from "@/components/listing-qa";
import { ReportContent } from "@/components/report-content";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { VerifiedMark } from "@/components/verified-badge";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

function careerStageLabel(value: string | null) {
  if (!value) return null;
  return CAREER_STAGES.find((stage) => stage.value === value)?.label ?? value;
}

function DetailField({
  icon: IconComponent,
  label,
  value,
}: {
  icon: Icon;
  label: string;
  value: ReactNode;
}) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <IconComponent className="h-3.5 w-3.5" aria-hidden />
        {label}
      </p>
      <div className="mt-1 text-sm font-semibold text-foreground">{value}</div>
    </div>
  );
}

export default async function ProjectDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    error?: string;
    applied?: string;
    reported?: string;
    published?: string;
  }>;
}) {
  const { id } = await params;
  const { error, applied, reported, published } = await searchParams;
  const project = await getProjectById(id);
  if (!project) notFound();

  const user = await getSessionUser();
  const isOwner = user?.id === project.ownerId;
  // Drafts are not public listings — only the owner can view them.
  if (project.status === "draft" && !isOwner) notFound();
  const ownerRole = careerStageLabel(project.ownerCareerStage);

  const [myApplication, allowance, questions] = await Promise.all([
    user && !isOwner ? getMyApplication(id, user.id) : Promise.resolve(null),
    user && !isOwner ? getApplicationAllowance(user.id) : Promise.resolve(null),
    getQuestionsForProject(id),
  ]);

  return (
    <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
      <Link
        href="/projects"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← All projects
      </Link>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}
      {reported && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          Thanks — your report has been received and will be reviewed.
        </div>
      )}
      {published && isOwner && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          <span>Your project is live.</span>
          <Link
            href="/available"
            className="font-medium text-primary hover:underline"
          >
            Browse people currently available →
          </Link>
        </div>
      )}
      {applied && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          Application submitted. Track it in{" "}
          <Link href="/applications" className="underline">
            My applications
          </Link>
          .
        </div>
      )}

      {/* --- Header: what it is, who posted it ------------------------- */}
      <div className="mt-5 flex flex-wrap items-center gap-1.5">
        {project.isBeginnerFriendly && (
          <Badge className="border-transparent bg-success text-success-foreground">
            Beginner friendly
          </Badge>
        )}
        <Badge variant="secondary">{projectTypeLabel(project.projectType)}</Badge>
        {project.status !== "open" && (
          <Badge variant="outline" className="capitalize">
            {project.status.replace("_", " ")}
          </Badge>
        )}
      </div>

      <h1 className="mt-3 min-w-0 break-words text-3xl font-semibold tracking-tight">
        {project.title}
      </h1>

      <p className="mt-3 flex flex-wrap items-center gap-x-1.5 text-sm text-muted-foreground">
        Posted by{" "}
        <Link
          href={`/profile/${project.ownerId}`}
          className="inline-flex items-center gap-1 font-medium text-foreground hover:underline"
        >
          {project.ownerName ?? "Unknown"}
          {project.ownerVerified && <VerifiedMark />}
        </Link>
        {(project.ownerUniversity || ownerRole) && (
          <span>
            · {[ownerRole, project.ownerUniversity].filter(Boolean).join(", ")}
          </span>
        )}
      </p>

      {/* --- Key facts: one quiet strip, no competing colour ------------ */}
      <Card className="mt-6">
        <CardContent className="grid grid-cols-2 gap-x-4 gap-y-5 text-sm sm:grid-cols-3">
          <DetailField
            icon={GraduationCap}
            label="Experience level"
            value={experienceLabel(project.experienceLevel)}
          />
          <DetailField
            icon={Stethoscope}
            label="Specialty"
            value={project.specialty ?? "Not set"}
          />
          <DetailField
            icon={Briefcase}
            label="Role"
            value={project.roleCategory ?? "Not set"}
          />
          <DetailField
            icon={UserPlus}
            label="Positions"
            value={project.positionsAvailable}
          />
          <DetailField
            icon={Users}
            label="Applications"
            value={project.applicationCount}
          />
          <DetailField
            icon={CalendarDays}
            label="Apply by"
            value={
              project.applicationDeadline
                ? formatDateUK(project.applicationDeadline)
                : "No deadline"
            }
          />
        </CardContent>
      </Card>

      {/* --- The listing itself ---------------------------------------- */}
      <section className="mt-8">
        <h2 className="text-lg font-semibold tracking-tight">
          About this project
        </h2>
        <p className="mt-3 max-w-[70ch] whitespace-pre-wrap text-[15px] leading-7 text-foreground">
          {project.description}
        </p>
      </section>

      {/* Owner controls */}
      {isOwner ? (
        <div className="mt-8 flex flex-wrap gap-2">
          <Link
            href={`/projects/${project.id}/applicants`}
            className={buttonVariants()}
          >
            View applicants ({project.applicationCount})
          </Link>
          <Link
            href={`/projects/${project.id}/edit`}
            className={buttonVariants({ variant: "outline" })}
          >
            Edit
          </Link>
          {project.status === "open" ? (
            <form action={closeProject}>
              <input type="hidden" name="id" value={project.id} />
              <Button type="submit" variant="outline">
                Close listing
              </Button>
            </form>
          ) : (
            <form action={reopenProject}>
              <input type="hidden" name="id" value={project.id} />
              <Button type="submit" variant="outline">
                Reopen listing
              </Button>
            </form>
          )}
          {project.status !== "completed" && (
            <form action={completeProject}>
              <input type="hidden" name="id" value={project.id} />
              <Button type="submit" variant="outline">
                Mark completed
              </Button>
            </form>
          )}
        </div>
      ) : (
        /* Applicant flow */
        <div className="mt-8">
          {!user ? (
            <Link href="/login" className={buttonVariants()}>
              Log in to apply
            </Link>
          ) : myApplication ? (
            <div className="rounded-lg border p-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">Your application</p>
                <Badge className={STATUS_BADGE_CLASS[myApplication.status]}>
                  {STATUS_LABELS[myApplication.status]}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Submitted {myApplication.createdAt.toLocaleDateString("en-GB")}.
                Track it in{" "}
                <Link href="/applications" className="underline">
                  My applications
                </Link>
                .
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {myApplication.status === "accepted" && (
                  <Link
                    href={`/projects/${project.id}/review/${project.ownerId}`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    Review supervisor
                  </Link>
                )}
              </div>
            </div>
          ) : project.status !== "open" ? (
            <Button disabled>Listing closed</Button>
          ) : allowance && allowance.remaining <= 0 ? (
            <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
              You&apos;ve used all {allowance.limit} of your applications this week.
              {allowance.resetsAt &&
                ` More open up on ${allowance.resetsAt.toLocaleDateString("en-GB")}.`}
            </div>
          ) : (
            <div className="rounded-lg border p-5">
              <h2 className="text-base font-semibold">Apply to this project</h2>
              <p className="mt-1 mb-4 text-sm text-muted-foreground">
                A focused application stands out. Be specific.
              </p>
              <ApplicationForm
                projectId={project.id}
                remaining={allowance?.remaining ?? 0}
                limit={allowance?.limit ?? 3}
              />
            </div>
          )}
        </div>
      )}

      <ListingQA
        projectId={project.id}
        questions={questions}
        isOwner={isOwner}
        isSignedIn={!!user}
        isOpen={project.status === "open"}
      />

      {user && !isOwner && (
        <div className="mt-10">
          <ReportContent
            targetType="project"
            targetId={project.id}
            backTo={`/projects/${project.id}`}
            label="Report this listing"
          />
        </div>
      )}
    </main>
  );
}
