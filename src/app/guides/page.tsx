import Link from "next/link";
import {
  BookOpenCheck,
  ClipboardPen,
  FileSearch,
  Rocket,
  ShieldCheck,
  Star,
} from "lucide-react";
import {
  DELIVERY_PROMISE,
  GUARANTEE_PARAGRAPHS,
  GUIDE_FAQ,
  HOW_IT_WORKS_STEPS,
  WHAT_IS_INCLUDED,
  formatPounds,
} from "@/lib/guides-meta";
import { getPricingState, getPublishedGuideReviews } from "@/lib/queries/guides";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";

export const metadata = {
  title: "Publication Guides — Symposed",
  description:
    "A bespoke, human-verified guide to your first publishable research project: a verified question, full search strategy, protocol and method walkthrough, delivered within 5 working days.",
};

const STEP_ICONS = [ClipboardPen, FileSearch, BookOpenCheck, Rocket];

function ReviewStars({ value }: { value: number }) {
  return (
    <span aria-label={`${value} out of 5`} className="text-amber-500">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          aria-hidden
          className={`inline h-3.5 w-3.5 ${i < value ? "fill-current" : "opacity-25"}`}
        />
      ))}
    </span>
  );
}

export default async function GuidesPage() {
  const [pricing, { reviews, average }] = await Promise.all([
    getPricingState(),
    getPublishedGuideReviews(),
  ]);
  const introActive = pricing.introRemainingPublic > 0;
  // Free launch mode: guides are simply free — no price, no counter, no
  // scarcity copy anywhere on the page.
  const freeMode = introActive && pricing.introPricePence === 0;

  return (
    <main className="flex-1">
      {/* ------------------------------------------------------- hero */}
      <section className="mx-auto w-full max-w-5xl px-6 pt-14 pb-12">
        <h1 className="max-w-2xl font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          A verified research question, and everything you need to answer it.
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Tell us your interests, and a person — not a pipeline — researches
          the literature, finds a question that is genuinely open and genuinely
          doable, and builds you a complete methodological foundation for your
          first publication.
        </p>
        {/* While guides are free, no pricing or scarcity messaging at all —
            the banner returns automatically once a real price is set. */}
        {!freeMode && (
          <div className="mt-6 inline-flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-secondary/50 px-4 py-3 text-sm">
            {introActive ? (
              <>
                <span className="font-semibold text-foreground">
                  Introductory price: {formatPounds(pricing.introPricePence)}{" "}
                  per guide for the first {pricing.introQuantity} guides.
                </span>
                <span className="font-medium text-primary">
                  {pricing.introRemainingPublic} of {pricing.introQuantity}{" "}
                  remaining.
                </span>
                <span className="w-full text-muted-foreground">
                  After the first {pricing.introQuantity} guides, the price
                  returns to {formatPounds(pricing.standardPricePence)} per
                  guide.
                </span>
              </>
            ) : (
              <span className="font-semibold text-foreground">
                {formatPounds(pricing.standardPricePence)} per guide — the
                total price, nothing added at checkout.
              </span>
            )}
          </div>
        )}
        <div className="mt-6">
          <Link href="/guides/request" className={buttonVariants({ size: "lg" })}>
            Start your guide
          </Link>
        </div>
      </section>

      {/* --------------------------------------------- what is included */}
      <section className="border-y bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-12">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            What is included
          </h2>
          <div className="mt-6 rounded-lg border bg-card p-6 sm:p-8">
            <ul className="grid gap-x-10 gap-y-5 sm:grid-cols-2">
              {WHAT_IS_INCLUDED.map(([lead, body]) => (
                <li key={lead} className="text-sm leading-relaxed">
                  <strong className="font-semibold text-foreground">
                    {lead}
                  </strong>{" "}
                  <span className="text-muted-foreground">{body}</span>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-5 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm font-semibold">
            {DELIVERY_PROMISE}
          </p>
        </div>
      </section>

      {/* ----------------------------------------------- how it works */}
      <section className="mx-auto w-full max-w-5xl px-6 py-12">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">
          How it works
        </h2>
        <ol className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {HOW_IT_WORKS_STEPS.map(([title, body], i) => {
            const StepIcon = STEP_ICONS[i];
            return (
              <li key={title}>
                <span className="inline-flex size-9 items-center justify-center rounded-md bg-primary/10">
                  <StepIcon className="h-5 w-5 text-primary" aria-hidden />
                </span>
                <h3 className="mt-3 text-sm font-semibold text-foreground">
                  {i + 1}. {title}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                  {body}
                </p>
              </li>
            );
          })}
        </ol>
      </section>

      {/* ------------------------------------------------------ price */}
      {!freeMode && (
        <section className="mx-auto w-full max-w-5xl px-6 pb-12">
          <div className="rounded-lg border p-6 sm:p-8">
            <h2 className="font-heading text-2xl font-semibold tracking-tight">
              Price and availability
            </h2>
            {introActive ? (
              <>
                <p className="mt-4 text-lg">
                  <strong>
                    Introductory price: {formatPounds(pricing.introPricePence)}{" "}
                    per guide for the first {pricing.introQuantity} guides.
                  </strong>{" "}
                  <span className="font-medium text-primary">
                    {pricing.introRemainingPublic} of {pricing.introQuantity}{" "}
                    remaining.
                  </span>
                </p>
                <p className="mt-2 text-muted-foreground">
                  After the first {pricing.introQuantity} guides, the price
                  returns to {formatPounds(pricing.standardPricePence)} per
                  guide.
                </p>
              </>
            ) : (
              <p className="mt-4 text-lg">
                <strong>
                  {formatPounds(pricing.standardPricePence)} per guide.
                </strong>
              </p>
            )}
            <p className="mt-3 text-sm text-muted-foreground">
              The price shown is the total you pay — VAT-inclusive where
              applicable, with no processing, booking or service fee added at
              checkout. The counter is real: it only moves when a guide is
              actually bought.
            </p>
          </div>
        </section>
      )}

      {/* ---------------------------------------------------- reviews */}
      {reviews.length > 0 && (
        <section className="border-y bg-secondary/50">
          <div className="mx-auto w-full max-w-5xl px-6 py-12">
            <div className="flex flex-wrap items-center gap-4">
              <h2 className="font-heading text-2xl font-semibold tracking-tight">
                What buyers say
              </h2>
              {average != null && (
                <span className="flex items-center gap-2 text-sm font-medium">
                  <ReviewStars value={Math.round(average)} />
                  {average.toFixed(1)} from {reviews.length} reviews
                </span>
              )}
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {reviews.map((r) => (
                <figure key={r.id} className="rounded-lg border bg-card p-5">
                  <div className="flex items-center justify-between gap-3">
                    <ReviewStars value={r.rating} />
                    <span className="text-xs text-muted-foreground">
                      {(r.publishedAt ?? r.createdAt).toLocaleDateString(
                        "en-GB",
                        { month: "long", year: "numeric" }
                      )}
                    </span>
                  </div>
                  <blockquote className="mt-3 text-sm leading-relaxed">
                    {r.body}
                  </blockquote>
                  <figcaption className="mt-3 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {r.reviewerName}
                    </span>{" "}
                    — {r.reviewerRole}
                    {r.reviewerInstitution ? `, ${r.reviewerInstitution}` : ""}
                    {r.guideTopic ? ` · ${r.guideTopic}` : ""}
                  </figcaption>
                  {r.complimentaryGuide && (
                    <Badge
                      variant="outline"
                      className="mt-3 border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
                    >
                      Received a complimentary guide
                    </Badge>
                  )}
                </figure>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* -------------------------------------------------- guarantee */}
      <section className="mx-auto w-full max-w-5xl px-6 py-12">
        <div className="max-w-3xl rounded-lg border-2 border-success/40 bg-success/5 p-6 sm:p-8">
          <h2 className="flex items-center gap-2 font-heading text-2xl font-semibold tracking-tight">
            <ShieldCheck className="h-6 w-6 text-success" aria-hidden />
            The guarantee
          </h2>
          {GUARANTEE_PARAGRAPHS.map((p, i) => (
            <p
              key={i}
              className={`mt-4 leading-relaxed ${i === 0 ? "font-medium" : "text-sm text-muted-foreground"}`}
            >
              {p}
            </p>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------- FAQ */}
      <section className="mx-auto w-full max-w-5xl px-6 pb-12">
        <h2 className="font-heading text-2xl font-semibold tracking-tight">
          Questions, answered
        </h2>
        <dl className="mt-6 max-w-3xl border-t">
          {GUIDE_FAQ.map(([q, a]) => (
            <div key={q} className="border-b py-4">
              <dt className="text-sm font-semibold">{q}</dt>
              <dd className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                {a}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* -------------------------------------------------- final CTA */}
      <section className="border-t bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-12">
          <h2 className="max-w-2xl font-heading text-2xl font-semibold tracking-tight [text-wrap:balance]">
            Stop looking for a project. Start one.
          </h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            The proforma takes about five minutes.{" "}
            {introActive &&
              !freeMode &&
              `${pricing.introRemainingPublic} discounted ${
                pricing.introRemainingPublic === 1 ? "guide" : "guides"
              } left at ${formatPounds(pricing.introPricePence)}.`}
          </p>
          <Link
            href="/guides/request"
            className={buttonVariants({ size: "lg", className: "mt-6" })}
          >
            Start your guide
          </Link>
        </div>
      </section>
    </main>
  );
}
