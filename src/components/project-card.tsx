import Link from "next/link";
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
import type { ComponentType, SVGProps } from "react";
import { projectTypeLabel, experienceLabel } from "@/lib/project-meta";
import { formatDateUK } from "@/lib/utils";
import { CAREER_STAGES } from "@/lib/profile";
import type { ProjectListItem } from "@/lib/queries/projects";
import { Badge } from "@/components/ui/badge";

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const TYPE_ICONS: Record<ProjectListItem["projectType"], Icon> = {
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

function ownerRole(value: string | null) {
  if (!value) return null;
  return CAREER_STAGES.find((stage) => stage.value === value)?.label ?? value;
}

function InfoPill({
  icon: IconComponent,
  label,
  className,
}: {
  icon: Icon;
  label: string;
  className: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${className}`}
    >
      <IconComponent className="h-3.5 w-3.5" aria-hidden />
      {label}
    </span>
  );
}

export function ProjectCard({ p }: { p: ProjectListItem }) {
  const TypeIcon = TYPE_ICONS[p.projectType];
  const ownerMeta = [p.ownerUniversity, ownerRole(p.ownerCareerStage)]
    .filter(Boolean)
    .join(" · ");

  return (
    <Link
      href={`/projects/${p.id}`}
      // A page of cards: viewport-prefetching every dynamic card re-fetches
      // endlessly (dynamic prefetches expire immediately) and starves real
      // navigations like the pagination links.
      prefetch={false}
      className="block rounded-lg border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 break-words font-semibold leading-snug text-card-foreground">
          {p.title}
        </h3>
        {p.isBeginnerFriendly && (
          <Badge className="shrink-0 border-transparent bg-success text-success-foreground">
            Beginner
          </Badge>
        )}
      </div>

      <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
        {p.description}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <InfoPill
          icon={TypeIcon}
          label={projectTypeLabel(p.projectType)}
          className="border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-300"
        />
        <InfoPill
          icon={GraduationCap}
          label={experienceLabel(p.experienceLevel)}
          className="border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
        />
        {p.specialty && (
          <InfoPill
            icon={Stethoscope}
            label={p.specialty}
            className="border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300"
          />
        )}
        {p.roleCategory && (
          <InfoPill
            icon={Briefcase}
            label={p.roleCategory}
            className="border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-900/60 dark:bg-violet-950/40 dark:text-violet-300"
          />
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <InfoPill
          icon={Users}
          label={`${p.applicationCount} application${p.applicationCount === 1 ? "" : "s"}`}
          className="border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
        />
        <InfoPill
          icon={UserPlus}
          label={`${p.positionsAvailable} spot${p.positionsAvailable === 1 ? "" : "s"}`}
          className="border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-900/60 dark:bg-teal-950/40 dark:text-teal-300"
        />
        {p.applicationDeadline && (
          <InfoPill
            icon={CalendarDays}
            label={`Apply by ${formatDateUK(p.applicationDeadline)}`}
            className="border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300"
          />
        )}
      </div>

      <div className="mt-3 text-xs text-muted-foreground">
        <span>{p.ownerName ?? "Unknown"}</span>
        {ownerMeta && <span> · {ownerMeta}</span>}
      </div>
    </Link>
  );
}
