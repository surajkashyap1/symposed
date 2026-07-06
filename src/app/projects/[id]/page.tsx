import Link from "next/link";
import { notFound } from "next/navigation";
import {
  BookOpen,
  Briefcase,
  CalendarDays,
  ClipboardList,
  FileText,
  GraduationCap,
  HelpCircle,
  Presentation,
  Search,
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
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const TYPE_ICONS: Record<string, Icon> = {
  audit: ClipboardList,
  systematic_review: Search,
  literature_review: BookOpen,
  case_study: FileText,
  retrospective: BookOpen,
  prospective_study: ClipboardList,
  poster: Presentation,
  teaching: GraduationCap,
  other: HelpCircle,
};

function careerStageLabel(value: string | null) {
  if (!value) return null;
  return CAREER_STAGES.find((stage) => stage.value === value)?.label ?? value;
}

function DetailField({
  icon: IconComponent,
  label,
  value,
  className,
}: {
  icon: Icon;
  label: string;
  value: ReactNode;
  className: string;
}) {
  return (
    <div className={`rounded-md border px-3 py-2 ${className}`}>
      <p className="flex items-center gap-1.5 text-xs font-medium">
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
  searchParams: Promise<{ error?: string; applied?: string }>;
}) {
  const { id } = await params;
  const { error, applied } = await searchParams;
  const project = await getProjectById(id);
  if (!project) notFound();

  const user = await getSessionUser();
  const isOwner = user?.id === project.ownerId;
  // Drafts are not public listings — only the owner can view them.
  if (project.status === "draft" && !isOwner) notFound();
  const ProjectTypeIcon = TYPE_ICONS[project.projectType] ?? HelpCircle;
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
      {applied && (
        <div className="mt-4 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
          Application submitted. Track it in{" "}
          <Link href="/applications" className="underline">
            My applications
          </Link>
          .
        </div>
      )}

      <div className="mt-4 flex items-start justify-between gap-4">
        <h1 className="min-w-0 break-words text-2xl font-semibold tracking-tight">
          {project.title}
        </h1>
        {project.status !== "open" && (
          <Badge variant="secondary" className="shrink-0 capitalize">
            {project.status.replace("_", " ")}
          </Badge>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {project.isBeginnerFriendly && (
          <Badge className="border-transparent bg-success text-success-foreground">
            Beginner friendly
          </Badge>
        )}
        <Badge variant="secondary">{projectTypeLabel(project.projectType)}</Badge>
        <Badge variant="outline">{experienceLabel(project.experienceLevel)}</Badge>
        {project.specialty && <Badge variant="outline">{project.specialty}</Badge>}
        {project.roleCategory && (
          <Badge variant="outline">{project.roleCategory}</Badge>
        )}
      </div>

      <p className="mt-6 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
        {project.description}
      </p>

      <Card className="mt-8">
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <DetailField
            icon={ProjectTypeIcon}
            label="Project type"
            value={projectTypeLabel(project.projectType)}
            className="border-sky-200 bg-sky-50 dark:border-sky-900/60 dark:bg-sky-950/40"
          />
          <DetailField
            icon={GraduationCap}
            label="Experience level"
            value={experienceLabel(project.experienceLevel)}
            className="border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/40"
          />
          <DetailField
            icon={Stethoscope}
            label="Specialty"
            value={project.specialty ?? "Not set"}
            className="border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/40"
          />
          <DetailField
            icon={Briefcase}
            label="Role"
            value={project.roleCategory ?? "Not set"}
            className="border-violet-200 bg-violet-50 dark:border-violet-900/60 dark:bg-violet-950/40"
          />
          <DetailField
            icon={Users}
            label="Applications"
            value={project.applicationCount}
            className="border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900"
          />
          <DetailField
            icon={UserPlus}
            label="Positions"
            value={project.positionsAvailable}
            className="border-teal-200 bg-teal-50 dark:border-teal-900/60 dark:bg-teal-950/40"
          />
          <DetailField
            icon={CalendarDays}
            label="Application deadline"
            value={
              project.applicationDeadline
                ? formatDateUK(project.applicationDeadline)
                : "Not set"
            }
            className="border-rose-200 bg-rose-50 dark:border-rose-900/60 dark:bg-rose-950/40"
          />
          <DetailField
            icon={Briefcase}
            label="Posted by"
            value={
              <Link href={`/profile/${project.ownerId}`} className="hover:underline">
                {project.ownerName ?? "Unknown"}
                {project.ownerUniversity ? `, ${project.ownerUniversity}` : ""}
                {ownerRole ? `, ${ownerRole}` : ""}
                {project.ownerVerified && (
                  <span className="ml-1 text-success" title="Verified">
                    ✓
                  </span>
                )}
              </Link>
            }
            className="border-indigo-200 bg-indigo-50 dark:border-indigo-900/60 dark:bg-indigo-950/40"
          />
        </CardContent>
      </Card>

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
    </main>
  );
}
