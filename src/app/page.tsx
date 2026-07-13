import Link from "next/link";
import { GraduationCap, ShieldCheck, Users } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { buttonVariants } from "@/components/ui/button";
import { LogoMark } from "@/components/logo";
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
      <section className="relative mx-auto w-full max-w-5xl overflow-hidden px-6 pt-16 pb-16 sm:pt-24">
        {/* Ambient brand mark: decorative only, clipped by the section. */}
        <LogoMark
          height={300}
          className="pointer-events-none absolute right-0 top-16 hidden text-primary/[0.05] lg:block"
        />
        <span className="inline-flex w-fit items-center gap-2 rounded-full border bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground">
          UK · students &amp; healthcare professionals
        </span>
        <h1 className="mt-6 max-w-3xl font-heading text-4xl font-semibold leading-tight tracking-tight text-foreground [text-wrap:balance] sm:text-5xl">
          Your first publication{" "}
          <span className="text-primary">starts here.</span>
        </h1>
        <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted-foreground">
          Symposed matches students and clinicians with real audits, reviews,
          case reports and posters — beginner-friendly projects first, so you
          don&apos;t need experience to get experience.
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
            {[
              [
                "Build your profile",
                "Say who you are, what you're interested in, and how much time you have. Verify a .ac.uk or NHS email for a trust badge.",
              ],
              [
                "Apply to a project",
                "Filter by specialty, type and experience level. A capped number of applications per week keeps every application meaningful.",
              ],
              [
                "Deliver and be cited",
                "Do the work, collect a review from your supervisor, and carry a verified track record into your next application.",
              ],
            ].map(([title, body], i) => (
              <li key={title}>
                <span
                  aria-hidden
                  className="font-heading text-3xl font-semibold text-primary/40"
                >
                  {i + 1}
                </span>
                <h3 className="mt-2 text-sm font-semibold text-foreground">
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
          <div className="rounded-lg bg-primary/[0.05] p-7">
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
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-6")}
            >
              Post a project
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
          Real, finishable projects — not vague promises of
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
      <section className="relative overflow-hidden border-y border-ink-foreground/10 bg-ink text-ink-foreground">
        <LogoMark
          height={300}
          className="pointer-events-none absolute -right-10 -bottom-24 hidden text-ink-foreground/[0.05] md:block"
        />
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
            Free for everyone — enforced automatically and by policy.
          </p>
          {!user && (
            <Link
              href="/signup"
              className={cn(buttonVariants({ size: "lg" }), "mt-8")}
            >
              Join Symposed
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
