import Link from "next/link";
import {
  Award,
  GraduationCap,
  Presentation,
  Send,
  ShieldCheck,
  UserRound,
  Users,
} from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PROJECT_TYPES: [string, string][] = [
  ["Audits & QIPs", "Completed audit cycles with a named supervisor and a defined standard."],
  ["Systematic & literature reviews", "Real reviews that need screeners, data extractors and writers."],
  ["Posters & presentations", "Conference-ready posters and talks built from real project data."],
  ["Case reports", "Interesting cases written up with the team that treated them."],
];

export default async function Home() {
  const user = await getSessionUser();

  return (
    <main className="flex-1">
      {/* ---------------------------------------------------------- hero */}
      <section className="mx-auto w-full max-w-5xl px-6 pt-16 pb-16 sm:pt-24">
        <h1 className="max-w-3xl font-heading text-4xl font-semibold leading-tight tracking-tight text-foreground [text-wrap:balance] sm:text-5xl">
          Your first publication{" "}
          <span className="text-primary">starts here.</span>
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted-foreground">
          Symposed matches students and clinicians with real audits, reviews,
          case reports and posters. Beginner-friendly projects come first, so
          you don&apos;t need experience to get experience.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          {user ? (
            <Link href="/dashboard" className={buttonVariants({ size: "lg" })}>
              Go to dashboard
            </Link>
          ) : (
            <>
              <Link href="/projects" className={buttonVariants({ size: "lg" })}>
                Browse open projects
              </Link>
              <Link
                href="/signup"
                className={buttonVariants({ variant: "outline", size: "lg" })}
              >
                Create a free account
              </Link>
            </>
          )}
        </div>
      </section>

      {/* -------------------------------------------------- how it works */}
      <section className="border-y bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-14">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            How it works
          </h2>
          <ol className="mt-8 grid gap-8 sm:grid-cols-3">
            {(
              [
                [
                  UserRound,
                  "Build your profile",
                  "Say who you are, what you're interested in, and how much time you have. Verify a .ac.uk or NHS email for a trust badge.",
                ],
                [
                  Send,
                  "Apply to a project",
                  "Filter by specialty, type and experience level. A capped number of applications per week keeps every application meaningful.",
                ],
                [
                  Award,
                  "Deliver and be cited",
                  "Do the work, collect a review from your supervisor, and carry a verified track record into your next application.",
                ],
              ] as const
            ).map(([StepIcon, title, body]) => (
              <li key={title}>
                <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
                  <StepIcon className="h-5 w-5 text-primary" aria-hidden />
                </span>
                <h3 className="mt-3 text-sm font-semibold text-foreground">
                  {title}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {body}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* -------------------------------------------------- two audiences */}
      <section className="mx-auto w-full max-w-5xl px-6 py-14">
        <div className="grid gap-6 md:grid-cols-2">
          <div className="rounded-lg border p-7">
            <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
              <GraduationCap className="h-5 w-5 text-primary" aria-hidden />
            </span>
            <h2 className="mt-4 font-heading text-xl font-semibold tracking-tight">
              Looking for your first project?
            </h2>
            <ul className="mt-4 flex flex-col gap-2.5 text-sm text-muted-foreground">
              {[
                "Beginner-friendly listings are ranked first by default",
                "Every listing states the expected output and time commitment",
                "Ask public questions before you apply",
                "Reviews from completed projects build your research CV",
              ].map((line) => (
                <li key={line} className="flex gap-2">
                  <span aria-hidden className="text-primary">
                    ·
                  </span>
                  {line}
                </li>
              ))}
            </ul>
            <Link
              href="/projects"
              className={cn(buttonVariants({ size: "sm" }), "mt-6")}
            >
              Find a project
            </Link>
          </div>

          <div className="rounded-lg border p-7">
            <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
              <Users className="h-5 w-5 text-primary" aria-hidden />
            </span>
            <h2 className="mt-4 font-heading text-xl font-semibold tracking-tight">
              Have a project that needs hands?
            </h2>
            <ul className="mt-4 flex flex-col gap-2.5 text-sm text-muted-foreground">
              {[
                "Reach motivated students and junior clinicians across the UK",
                "Applicants come with profiles, reviews and reliability scores",
                "Application limits mean fewer, better-considered applicants",
                "Supporting beginners earns you a Research Mentor badge",
              ].map((line) => (
                <li key={line} className="flex gap-2">
                  <span aria-hidden className="text-primary">
                    ·
                  </span>
                  {line}
                </li>
              ))}
            </ul>
            <Link
              href={user ? "/projects/new" : "/signup"}
              className={cn(buttonVariants({ size: "sm" }), "mt-6")}
            >
              Post a project
            </Link>
          </div>
        </div>
      </section>

      {/* ------------------------------------ guides + the other routes in */}
      <section className="mx-auto w-full max-w-5xl px-6 pb-14">
        {/* The revenue product gets the committed surface (spec §6.1). */}
        <div className="rounded-lg bg-primary p-8 text-primary-foreground sm:p-10">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-xl">
              <h2 className="font-heading text-2xl font-semibold tracking-tight [text-wrap:balance]">
                Can&apos;t find a project? Start your own — with a verified
                question.
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-primary-foreground/85">
                A Publication Guide gives you a research question checked
                against the literature, a full search strategy, protocol and
                method walkthrough — researched and verified by a person, built
                around your interests, delivered within 5 working days.
              </p>
            </div>
            <Link
              href="/guides"
              className={cn(
                buttonVariants({ size: "lg" }),
                "border border-primary-foreground/20 bg-background text-foreground hover:bg-background/90"
              )}
            >
              Explore Publication Guides
            </Link>
          </div>
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <div className="rounded-lg border p-7">
            <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
              <UserRound className="h-5 w-5 text-primary" aria-hidden />
            </span>
            <h2 className="mt-4 font-heading text-xl font-semibold tracking-tight">
              Advertise yourself to listers
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Post a free listing on the People board — your skills, your
              availability, what you&apos;re looking for — and let project
              leads come to you.
            </p>
            <Link
              href="/available"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-5")}
            >
              See who&apos;s available
            </Link>
          </div>
          <div className="rounded-lg border p-7">
            <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
              <Presentation className="h-5 w-5 text-primary" aria-hidden />
            </span>
            <h2 className="mt-4 font-heading text-xl font-semibold tracking-tight">
              Teach, and be able to prove it
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Deliver a live teaching series to a national audience, reviewed
              by a specialist, with a documented evidence trail of exactly what
              you taught. Free to create and attend.
            </p>
            <Link
              href="/teach"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-5")}
            >
              Teach on Symposed
            </Link>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------- project types */}
      <section className="mx-auto w-full max-w-5xl px-6 pb-16">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">
          Work that becomes a line on your CV
        </h2>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Real, finishable projects, not vague promises of
          &ldquo;involvement&rdquo;.
        </p>
        <dl className="mt-8 border-t">
          {PROJECT_TYPES.map(([name, desc]) => (
            <div
              key={name}
              className="grid gap-1 border-b py-5 sm:grid-cols-[2fr_3fr] sm:gap-8"
            >
              <dt className="font-heading text-lg font-semibold text-primary">
                {name}
              </dt>
              <dd className="text-sm leading-relaxed text-muted-foreground sm:self-center">
                {desc}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ------------------------------------------- statement + close */}
      {/* A closing sales pitch: only shown to visitors who can still act on it.
          Signed-in users otherwise see a dark band with no purpose. */}
      {!user && (
        <section className="border-y border-ink-foreground/10 bg-ink text-ink-foreground">
          <div className="mx-auto w-full max-w-5xl px-6 py-16">
            <div className="flex items-center gap-2 text-ink-foreground/70">
              <ShieldCheck className="h-4 w-4" aria-hidden />
              <span className="text-sm">Built on verified trust</span>
            </div>
            <p className="mt-4 max-w-2xl font-heading text-2xl font-medium leading-snug [text-wrap:balance] sm:text-3xl">
              Posters verify institutional emails. Reviews come only from
              completed projects. No patient data, anywhere.
            </p>
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-foreground/70">
              Free for everyone, enforced automatically and by policy.
            </p>
            <Link
              href="/signup"
              className={cn(buttonVariants({ size: "lg" }), "mt-8")}
            >
              Join Symposed
            </Link>
          </div>
        </section>
      )}
    </main>
  );
}
