import Link from "next/link";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { getSessionUser, getProfile } from "@/lib/auth";
import {
  listOpenProjects,
  type CompetitivenessRank,
} from "@/lib/queries/projects";
import { ProjectCard } from "@/components/project-card";
import {
  PROJECT_TYPES,
  EXPERIENCE_LEVELS,
  PROJECT_TYPE_VALUES,
  EXPERIENCE_VALUES,
  type ProjectType,
  type ExperienceLevel,
} from "@/lib/project-meta";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button, buttonVariants } from "@/components/ui/button";

type SP = {
  q?: string;
  specialty?: string;
  type?: string;
  experience?: string;
  rank?: string;
  page?: string;
};

const COMPETITIVENESS_RANKS: {
  value: CompetitivenessRank;
  label: string;
}[] = [
  { value: "beginner_first", label: "Beginner-friendly first" },
  { value: "competitive_first", label: "Competitive first" },
];

export default async function ProjectsPage({
  searchParams,
}: {
  searchParams: Promise<SP>;
}) {
  const sp = await searchParams;
  const user = await getSessionUser();
  const canPost = user ? (await getProfile(user.id))?.isVerified ?? false : false;

  const rank = COMPETITIVENESS_RANKS.some((r) => r.value === sp.rank)
    ? (sp.rank as CompetitivenessRank)
    : "beginner_first";
  const type = PROJECT_TYPE_VALUES.has(sp.type as ProjectType)
    ? (sp.type as ProjectType)
    : undefined;
  const experience = EXPERIENCE_VALUES.has(sp.experience as ExperienceLevel)
    ? (sp.experience as ExperienceLevel)
    : undefined;
  const q = sp.q?.trim() || undefined;
  const specialty = sp.specialty?.trim() || undefined;
  const requestedPage = Number.parseInt(sp.page ?? "1", 10) || 1;

  const { items: projects, total, page, pageCount } = await listOpenProjects({
    q,
    specialty,
    type,
    experience,
    rank,
    page: requestedPage,
  });

  // Link to another page keeping the current filters.
  const pageHref = (p: number) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (specialty) params.set("specialty", specialty);
    if (type) params.set("type", type);
    if (experience) params.set("experience", experience);
    if (rank !== "beginner_first") params.set("rank", rank);
    if (p > 1) params.set("page", String(p));
    const qs = params.toString();
    return qs ? `/projects?${qs}` : "/projects";
  };

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Research projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse open opportunities. {total} open{" "}
            {total === 1 ? "project" : "projects"}.
          </p>
        </div>
        {canPost && (
          <Link href="/projects/new" className={buttonVariants({ className: "gap-1.5" })}>
            <Plus className="h-4 w-4" aria-hidden />
            Post a project
          </Link>
        )}
      </div>

      {/* Filters (GET form) */}
      <form className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Input name="q" placeholder="Search title or description" defaultValue={q ?? ""} />
        <Input name="specialty" placeholder="Specialty" defaultValue={specialty ?? ""} />
        <Select
          name="type"
          defaultValue={type ?? ""}
          options={[{ value: "", label: "Any type" }, ...PROJECT_TYPES]}
        />
        <Select
          name="experience"
          defaultValue={experience ?? ""}
          options={[{ value: "", label: "Any level" }, ...EXPERIENCE_LEVELS]}
        />
        <div className="flex gap-2">
          <Select
            name="rank"
            defaultValue={rank}
            className="flex-1"
            options={COMPETITIVENESS_RANKS}
          />
          <Button type="submit" variant="outline">
            Filter
          </Button>
        </div>
      </form>

      {/* Results */}
      {projects.length === 0 ? (
        <div className="mt-12 rounded-lg border border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">
            No projects match. Try clearing filters
            {canPost ? ", or be the first to post one." : "."}
          </p>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {projects.map((p) => (
            <ProjectCard key={p.id} p={p} />
          ))}
        </div>
      )}

      {pageCount > 1 && (
        <nav
          aria-label="Pagination"
          className="mt-10 flex items-center justify-center gap-3"
        >
          {page > 1 ? (
            <Link
              href={pageHref(page - 1)}
              prefetch={false}
              rel="prev"
              className={buttonVariants({ variant: "outline", className: "gap-1" })}
            >
              <ChevronLeft className="h-4 w-4" aria-hidden />
              Previous
            </Link>
          ) : (
            <span className={buttonVariants({ variant: "outline", className: "gap-1 pointer-events-none opacity-50" })}>
              <ChevronLeft className="h-4 w-4" aria-hidden />
              Previous
            </span>
          )}
          <span className="text-sm text-muted-foreground">
            Page {page} of {pageCount}
          </span>
          {page < pageCount ? (
            <Link
              href={pageHref(page + 1)}
              prefetch={false}
              rel="next"
              className={buttonVariants({ variant: "outline", className: "gap-1" })}
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden />
            </Link>
          ) : (
            <span className={buttonVariants({ variant: "outline", className: "gap-1 pointer-events-none opacity-50" })}>
              Next
              <ChevronRight className="h-4 w-4" aria-hidden />
            </span>
          )}
        </nav>
      )}
    </main>
  );
}
