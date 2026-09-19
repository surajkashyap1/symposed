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
  GUIDE_PANELS,
  HERO_DESCRIPTION,
  HOW_IT_WORKS_STEPS,
  METHOD_STATEMENT,
  formatPounds,
} from "@/lib/guides-meta";
import {
  getPricingState,
  getPublishedGuideReviews,
  type PricingState,
} from "@/lib/queries/guides";
import { GuidePanels } from "@/components/guide-panels";
import { ListingBenefits } from "@/components/listing-benefits";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";

export const metadata = {
  title: "Publication Guides | Symposed",
  description:
    "A bespoke, verified guide to your first publishable review: a verified question, full search strategy, protocol and method walkthrough, delivered within 7 working days.",
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

// Amendment §2 price block. The free line and the standard line appear
// together at all times so the value of the free allocation is visible; the
// middle (£25) tier line shows only while it is the operative band or the
// next one up. When the free count reaches zero the free line is removed
// rather than left showing zero.
function PriceBlock({ pricing }: { pricing: PricingState }) {
  const hasMiddle =
    pricing.introQuantity > 0 &&
    pricing.introPricePence > 0 &&
    pricing.introPricePence < pricing.standardPricePence;
  const freeLeft = pricing.freeRemainingPublic;
  const introLeft = pricing.introRemainingPublic;

  return (
    <div className="flex flex-col gap-1 text-sm">
      {freeLeft > 0 && (
        <p>
          <span className="font-semibold text-foreground">
            The first {pricing.freeQuantity} guides are free.
          </span>{" "}
          <span className="font-medium text-primary">
            {freeLeft} of {pricing.freeQuantity} remaining.
          </span>
        </p>
      )}
      {hasMiddle && introLeft > 0 && (
        <p className="text-muted-foreground">
          The next {pricing.introQuantity} guides are{" "}
          {formatPounds(pricing.introPricePence)} each
          {freeLeft === 0 && (
            <>
              {" "}
              <span className="font-medium text-primary">
                ({introLeft} of {pricing.introQuantity} remaining)
              </span>
            </>
          )}
          .
        </p>
      )}
      <p className={freeLeft > 0 || introLeft > 0 ? "text-muted-foreground" : "font-semibold text-foreground"}>
        {freeLeft > 0 || (hasMiddle && introLeft > 0)
          ? `After that, guides are ${formatPounds(pricing.standardPricePence)} each.`
          : `Guides are ${formatPounds(pricing.standardPricePence)} each, the total price, nothing added at checkout.`}
      </p>
    </div>
  );
}

export default async function GuidesPage() {
  const [pricing, { reviews, average }] = await Promise.all([
    getPricingState(),
    getPublishedGuideReviews(),
  ]);

  return (
    <main className="flex-1">
      {/* ------------------------------------------------------- hero */}
      <section className="mx-auto w-full max-w-5xl px-6 pt-14 pb-12">
        <h1 className="max-w-2xl font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          A verified research question, and everything you need to answer it.
        </h1>
        <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          {HERO_DESCRIPTION}
        </p>
        <p className="mt-4 max-w-2xl text-base font-medium leading-relaxed text-foreground">
          {METHOD_STATEMENT}
        </p>
        <div className="mt-6 inline-flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-secondary/50 px-4 py-3">
          <PriceBlock pricing={pricing} />
        </div>
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
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            What we build depends on your review type. Swipe or use the arrows
            to see each one.
          </p>
          <GuidePanels panels={GUIDE_PANELS} />
          <p className="mt-6 rounded-md border border-success/30 bg-success/10 px-4 py-3 text-sm font-semibold">
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
      <section className="mx-auto w-full max-w-5xl px-6 pb-12">
        <div className="rounded-lg border p-6 sm:p-8">
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            Price and availability
          </h2>
          <div className="mt-4">
            <PriceBlock pricing={pricing} />
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            The price shown is the total you pay: VAT-inclusive where
            applicable, with no processing, booking or service fee added at
            checkout. The counter is real. It only moves when a guide is
            actually delivered.
          </p>
        </div>
      </section>

      {/* -------------------------------------- list your project (§8) */}
      <section className="border-t bg-secondary/50">
        <div className="mx-auto w-full max-w-5xl px-6 py-12">
          <ListingBenefits />
        </div>
      </section>

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
                    ({r.reviewerRole}
                    {r.reviewerInstitution ? `, ${r.reviewerInstitution}` : ""}
                    {r.guideTopic ? ` · ${r.guideTopic}` : ""})
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
            Our commitment
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
            The proforma takes about five minutes.
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
