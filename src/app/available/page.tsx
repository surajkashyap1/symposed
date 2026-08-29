import Link from "next/link";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import {
  listAvailability,
  getMyListing,
} from "@/lib/queries/availability";
import { SKILLS_OFFERED } from "@/lib/board-meta";
import { CAREER_STAGES } from "@/lib/profile";
import {
  markListingFound,
  removeListing,
  renewListing,
} from "@/app/available/actions";
import { AvailabilityCard } from "@/components/availability-card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button, buttonVariants } from "@/components/ui/button";

export const metadata = {
  title: "Available for projects — Symposed",
  description:
    "Students and clinicians currently looking to join research projects. Advertise yourself and let listers come to you.",
};

type SP = {
  q?: string;
  specialty?: string;
  skill?: string;
  stage?: string;
  region?: string;
  hours?: string;
  page?: string;
  posted?: string;
  renewed?: string;
  found?: string;
  removed?: string;
};

const HOURS_OPTIONS = [
  { value: "", label: "Any availability" },
  { value: "3", label: "3+ hrs/week" },
  { value: "5", label: "5+ hrs/week" },
  { value: "10", label: "10+ hrs/week" },
];

export default async function AvailablePage({
  searchParams,
}: {
  searchParams: Promise<SP>;
}) {
  const sp = await searchParams;
  const user = await getSessionUser();
  const myListing = user ? await getMyListing(user.id) : null;

  const q = sp.q?.trim() || undefined;
  const specialty = sp.specialty?.trim() || undefined;
  const skill = SKILLS_OFFERED.some((s) => s === sp.skill) ? sp.skill : undefined;
  const stage = CAREER_STAGES.some((s) => s.value === sp.stage)
    ? sp.stage
    : undefined;
  const region = sp.region?.trim() || undefined;
  const minHours = ["3", "5", "10"].includes(sp.hours ?? "")
    ? Number(sp.hours)
    : undefined;
  const requestedPage = Number.parseInt(sp.page ?? "1", 10) || 1;

  const { items, total, page, pageCount } = await listAvailability({
    q,
    specialty,
    skill,
    careerStage: stage,
    region,
    minHours,
    page: requestedPage,
  });

  const pageHref = (p: number) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (specialty) params.set("specialty", specialty);
    if (skill) params.set("skill", skill);
    if (stage) params.set("stage", stage);
    if (region) params.set("region", region);
    if (minHours) params.set("hours", String(minHours));
    if (p > 1) params.set("page", String(p));
    const qs = params.toString();
    return qs ? `/available?${qs}` : "/available";
  };

  const myListingLive = myListing?.isLive ?? false;

  const banner = sp.posted
    ? "Your listing is live. Listers can now find you."
    : sp.renewed
      ? "Listing renewed — it's back at the top of the board for another 60 days."
      : sp.found
        ? "Brilliant news. Your listing has been taken off the board."
        : sp.removed
          ? "Your listing has been removed from the board."
          : null;

  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
      {banner && (
        <div className="mb-6 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm">
          {banner}
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Available for projects
          </h1>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            People ready to join a project now. {total}{" "}
            {total === 1 ? "person" : "people"} currently available.{" "}
            <Link href="/projects" className="text-primary hover:underline">
              Looking for a project instead? Browse open positions.
            </Link>
          </p>
        </div>
        {user && !myListing && (
          <Link
            href="/available/new"
            className={buttonVariants({ className: "gap-1.5" })}
          >
            <Plus className="h-4 w-4" aria-hidden />
            Advertise yourself
          </Link>
        )}
        {!user && (
          <Link href="/login" className={buttonVariants({ variant: "outline" })}>
            Log in to advertise yourself
          </Link>
        )}
      </div>

      {/* Manage strip for the caller's own listing */}
      {myListing && (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-secondary/50 px-4 py-3 text-sm">
          {myListingLive ? (
            <p>
              Your listing is <span className="font-medium">live</span> until{" "}
              {myListing.expiresAt.toLocaleDateString("en-GB")}.
            </p>
          ) : myListing.status === "found_project" ? (
            <p>
              Your listing is marked as{" "}
              <span className="font-medium">found a project</span>. Post it
              again any time.
            </p>
          ) : (
            <p>
              Your listing is{" "}
              <span className="font-medium">
                {myListing.status === "removed" ? "removed" : "expired"}
              </span>{" "}
              and not visible on the board.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Link
              href="/available/new"
              className={buttonVariants({ variant: "outline", size: "sm" })}
            >
              {myListingLive ? "Edit" : "Edit & republish"}
            </Link>
            {myListingLive ? (
              <>
                <form action={renewListing}>
                  <Button type="submit" variant="outline" size="sm">
                    Renew for 60 days
                  </Button>
                </form>
                <form action={markListingFound}>
                  <Button type="submit" variant="outline" size="sm">
                    I found a project
                  </Button>
                </form>
                <form action={removeListing}>
                  <Button type="submit" variant="ghost" size="sm">
                    Remove
                  </Button>
                </form>
              </>
            ) : (
              <form action={renewListing}>
                <Button type="submit" size="sm">
                  Reactivate
                </Button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Filters (GET form) */}
      <form className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Input
          name="q"
          placeholder="Search headlines and descriptions"
          defaultValue={q ?? ""}
        />
        <Input
          name="specialty"
          placeholder="Specialty interest"
          defaultValue={specialty ?? ""}
        />
        <Select
          name="skill"
          defaultValue={skill ?? ""}
          options={[
            { value: "", label: "Any skill" },
            ...SKILLS_OFFERED.map((s) => ({ value: s, label: s })),
          ]}
        />
        <Select
          name="stage"
          defaultValue={stage ?? ""}
          options={[
            { value: "", label: "Any grade or role" },
            ...CAREER_STAGES.map((s) => ({ value: s.value, label: s.label })),
          ]}
        />
        <Input
          name="region"
          placeholder="Location or region"
          defaultValue={region ?? ""}
        />
        <div className="flex gap-2">
          <Select
            name="hours"
            defaultValue={minHours ? String(minHours) : ""}
            className="flex-1"
            options={HOURS_OPTIONS}
          />
          <Button type="submit" variant="outline">
            Filter
          </Button>
        </div>
      </form>

      {/* Results */}
      {items.length === 0 ? (
        <div className="mt-12 rounded-lg border border-dashed p-10 text-center">
          <p className="text-sm text-muted-foreground">
            No one matches those filters right now.
          </p>
          <p className="mt-2 text-sm">
            {myListingLive ? (
              "Try broadening your search."
            ) : (
              <>
                Be the first —{" "}
                <Link
                  href={user ? "/available/new" : "/login"}
                  className="text-primary hover:underline"
                >
                  post your own listing
                </Link>{" "}
                and let listers come to you.
              </>
            )}
          </p>
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {items.map((l) => (
            <AvailabilityCard key={l.id} l={l} />
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
