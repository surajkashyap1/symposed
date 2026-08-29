import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { getSessionUser } from "@/lib/auth";
import { listTeachingTopics, getMyLatestSubmission } from "@/lib/queries/teaching";
import {
  SUBMISSION_STATUS_LABELS,
  TEACHING_RUBRIC,
  TOPIC_STATUS_LABELS,
} from "@/lib/teach-meta";
import { formatDateUK } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";

export const metadata = {
  title: "Teach on Symposed",
  description:
    "Create and deliver a teaching series through Symposed, with verifiable evidence of what you delivered. Free to create, free to attend.",
};

const BENEFITS: [string, string][] = [
  [
    "Evidence you can actually use.",
    "We provide a programme timetable, attendance records, aggregated written feedback with response rates, and a signed confirmation letter from Symposed setting out exactly what you delivered and when.",
  ],
  [
    "A sustained programme, not a one-off talk.",
    "Series run across 8 to 12 weeks. Many specialty person specifications distinguish between a single session and a programme delivered over months, and reward the latter far more highly.",
  ],
  [
    "A national audience.",
    "Teaching organised through Symposed reaches students and doctors across the UK, not only your own hospital.",
  ],
  [
    "Content reviewed by a specialist.",
    "Every course is checked for accuracy and safety by a GMC-registered clinician before it goes live.",
  ],
  [
    "You keep the credit.",
    "The course carries your name. Symposed provides the platform and the evidence trail.",
  ],
  [
    "It is free.",
    "No charge to create, host or deliver a course, and no charge to attend one.",
  ],
];

const TOPIC_STATUS_CLASS: Record<string, string> = {
  accepting_submissions: "border-transparent bg-success text-success-foreground",
  under_review:
    "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
  filled: "bg-secondary text-secondary-foreground",
};

export default async function TeachPage() {
  const user = await getSessionUser();
  const [topics, mySubmission] = await Promise.all([
    listTeachingTopics(),
    user ? getMyLatestSubmission(user.id) : Promise.resolve(null),
  ]);

  return (
    <main className="flex-1">
      {/* Hero */}
      <section className="mx-auto w-full max-w-5xl px-6 pt-14 pb-10">
        <h1 className="max-w-2xl font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          Teach through Symposed
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Design and deliver a live teaching series to students and doctors
          across the UK — and walk away with a documented, verifiable record of
          exactly what you taught.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/teach/apply" className={buttonVariants({ size: "lg" })}>
            Propose a course
          </Link>
          <a
            href="#topics"
            className={buttonVariants({ variant: "outline", size: "lg" })}
          >
            See commissioned topics
          </a>
        </div>
        {mySubmission && (
          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border bg-secondary/50 px-4 py-3 text-sm">
            <span>
              Your submission &ldquo;{mySubmission.title}&rdquo; is{" "}
              <span className="font-medium">
                {SUBMISSION_STATUS_LABELS[mySubmission.status]}
              </span>
              .
            </span>
            {mySubmission.status === "revisions_requested" && (
              <Link
                href="/teach/apply"
                className="font-medium text-primary hover:underline"
              >
                Revise and resubmit →
              </Link>
            )}
          </div>
        )}
      </section>

      {/* Benefits */}
      <section className="border-y bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-12">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            Why create teaching content
          </h2>
          <ul className="mt-6 grid gap-x-10 gap-y-6 sm:grid-cols-2">
            {BENEFITS.map(([lead, body]) => (
              <li key={lead} className="text-sm leading-relaxed">
                <strong className="font-semibold text-foreground">{lead}</strong>{" "}
                <span className="text-muted-foreground">{body}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Portfolio disclaimer — verbatim, visually distinct, never hidden */}
      <section className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-6 text-sm leading-relaxed text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
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
            all. Some require teaching to have been delivered live rather than
            as pre-recorded material.
          </p>
          <p className="mt-3">
            Symposed provides accurate evidence of the teaching you actually
            delivered. How that evidence scores, and whether it counts at all,
            is determined entirely by your specialty&apos;s published criteria,
            which you must check yourself before making any claim. We make no
            guarantee about points.
          </p>
          <p className="mt-3">
            You must be able to evidence every claim you make in a training
            application, and applications are subject to audit. Symposed will
            confirm what happened and nothing more.
          </p>
        </div>
      </section>

      {/* Commissioned topics */}
      <section id="topics" className="mx-auto w-full max-w-5xl scroll-mt-20 px-6 py-6">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">
          Topics we&apos;re commissioning now
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Apply for one of these, or propose your own idea — both go through
          the same review. Several accepted contributors may share a series.
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {topics.map((t) => (
            <div key={t.id} className="flex flex-col rounded-lg border bg-card p-5">
              <div className="flex items-start justify-between gap-2">
                <Badge className={TOPIC_STATUS_CLASS[t.status] ?? ""}>
                  {TOPIC_STATUS_LABELS[t.status] ?? t.status}
                </Badge>
                {t.deadline && (
                  <span className="text-xs text-muted-foreground">
                    Apply by {formatDateUK(t.deadline)}
                  </span>
                )}
              </div>
              <h3 className="mt-3 font-semibold leading-snug text-card-foreground">
                {t.title}
              </h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                {t.description}
              </p>
              <p className="mt-3 text-xs font-medium text-muted-foreground">
                {t.format}
              </p>
              {t.status === "accepting_submissions" && (
                <Link
                  href={`/teach/apply?topic=${t.id}`}
                  className={buttonVariants({ size: "sm", className: "mt-4 self-start" })}
                >
                  Apply for this topic
                </Link>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Live vs recorded */}
      <section className="mx-auto w-full max-w-5xl px-6 py-10">
        <div className="max-w-2xl rounded-lg border bg-card p-6">
          <h2 className="text-lg font-semibold tracking-tight">
            Why we run courses live
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            We run courses live wherever possible. Some specialty criteria will
            not accept self-paced material without a live tutor, so a live
            series protects your evidence. Recordings are released afterwards
            for people who could not attend.
          </p>
        </div>
      </section>

      {/* The rubric */}
      <section className="border-t bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-12">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            How submissions are assessed
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Rolling review against this rubric — not a competition. If your
            submission needs work, you get specific written feedback and can
            resubmit.
          </p>
          <dl className="mt-6 max-w-3xl border-t">
            {TEACHING_RUBRIC.map((r) => (
              <div
                key={r.criterion}
                className="grid gap-1 border-b py-4 sm:grid-cols-[1fr_2fr] sm:gap-8"
              >
                <dt className="text-sm font-semibold">{r.criterion}</dt>
                <dd className="text-sm leading-relaxed text-muted-foreground">
                  {r.standard}
                </dd>
              </div>
            ))}
          </dl>
          <Link
            href="/teach/apply"
            className={buttonVariants({ size: "lg", className: "mt-8" })}
          >
            Propose a course
          </Link>
        </div>
      </section>
    </main>
  );
}
