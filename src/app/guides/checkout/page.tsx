import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { getOrderForUser, getPricingState } from "@/lib/queries/guides";
import {
  DELIVERY_PROMISE,
  formatPounds,
  formatPriceLabel,
  traderInfo,
} from "@/lib/guides-meta";
import { startGuideCheckout } from "@/app/guides/actions";
import { isUuid } from "@/lib/utils";
import { GuideConsentGate } from "@/components/guide-consent-gate";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Review your guide request — Symposed" };

const PROFORMA_LABELS: [string, string][] = [
  ["grade", "Grade or role"],
  ["institution", "Institution"],
  ["publicationType", "Publication type"],
  ["topics", "Topic areas"],
  ["existingTitle", "Title in mind"],
  ["hoursPerWeek", "Hours per week"],
  ["timeline", "Timeline"],
  ["statsConfidence", "Statistical confidence"],
  ["supervisor", "Supervisor"],
];

export default async function GuideCheckoutPage({
  searchParams,
}: {
  searchParams: Promise<{
    order?: string;
    error?: string;
    blocked?: string;
    priceChanged?: string;
  }>;
}) {
  const user = await requireUser();
  const { order: orderId, error, blocked, priceChanged } = await searchParams;
  if (!orderId || !isUuid(orderId)) notFound();

  const [order, pricing] = await Promise.all([
    getOrderForUser(orderId, user.id),
    getPricingState(),
  ]);
  if (!order) notFound();
  if (order.status !== "submitted") redirect(`/guides/thanks?order=${orderId}`);

  const proforma = JSON.parse(order.proforma) as Record<string, unknown>;
  const trader = traderInfo();

  // The price the user is about to be charged (re-resolved server-side at the
  // moment of payment; a change forces the explicit confirmation below).
  const currentPence =
    pricing.introRemainingPublic > 0
      ? pricing.introPricePence
      : pricing.standardPricePence;
  const displayPence = priceChanged
    ? Number.parseInt(priceChanged, 10) || currentPence
    : currentPence;

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Link
        href="/guides/request"
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        ← Edit your answers
      </Link>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Review your request</CardTitle>
          <CardDescription>{DELIVERY_PROMISE}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          {blocked && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
              Sorry — guides aren&apos;t available for purchase from your
              country yet, because of the tax registration each market
              requires. Nothing has been charged. If you think this is wrong,
              please{" "}
              <Link href="/contact" className="underline">
                contact us
              </Link>
              .
            </div>
          )}
          {priceChanged && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
              The introductory guides sold out while you had this page open.
              The price is now{" "}
              <strong>{formatPounds(displayPence)}</strong>. Nothing has been
              charged — if you&apos;re happy with the new price, confirm below.
            </div>
          )}
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Order summary */}
          <div>
            <h2 className="text-base font-semibold">Your answers</h2>
            <dl className="mt-3 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
              {PROFORMA_LABELS.map(([key, label]) => {
                const value = proforma[key];
                if (value == null || value === "") return null;
                return (
                  <div key={key} className={key === "topics" ? "sm:col-span-2" : ""}>
                    <dt className="text-muted-foreground">{label}</dt>
                    <dd className="mt-0.5 font-medium">{String(value)}</dd>
                  </div>
                );
              })}
              {Array.isArray(proforma.specialties) &&
                proforma.specialties.length > 0 && (
                  <div>
                    <dt className="text-muted-foreground">Specialties</dt>
                    <dd className="mt-0.5 font-medium">
                      {(proforma.specialties as string[]).join(", ")}
                    </dd>
                  </div>
                )}
              {Array.isArray(proforma.databases) &&
                proforma.databases.length > 0 && (
                  <div>
                    <dt className="text-muted-foreground">Database access</dt>
                    <dd className="mt-0.5 font-medium">
                      {(proforma.databases as string[]).join(", ")}
                    </dd>
                  </div>
                )}
            </dl>
          </div>

          {/* Price */}
          <div className="rounded-lg border bg-secondary/50 px-5 py-4">
            <p className="flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium">
                Symposed Publication Guide — bespoke, researched and verified
                by a person
              </span>
              <span className="text-xl font-semibold">
                {formatPriceLabel(displayPence)}
              </span>
            </p>
            <p className="mt-1.5 text-xs text-muted-foreground">
              {displayPence === 0
                ? "Free — no card needed, nothing to pay."
                : "Total price. No fees or taxes are added at checkout."}
              {displayPence > 0 &&
                pricing.introRemainingPublic > 0 &&
                displayPence === pricing.introPricePence &&
                ` ${pricing.introRemainingPublic} of ${pricing.introQuantity} introductory guides remaining; verified again when you confirm.`}
            </p>
          </div>

          {/* Pre-contract information (CCR 2013, spec §7.2) */}
          <div className="rounded-md border px-4 py-3 text-xs leading-relaxed text-muted-foreground">
            <p>
              <strong className="text-foreground">Who you&apos;re buying from:</strong>{" "}
              {trader.name} · {trader.address} · Contact: {trader.email}
            </p>
            <p className="mt-2">
              <strong className="text-foreground">What you&apos;re buying:</strong>{" "}
              a bespoke research guide, individually researched, written and
              verified by a person, delivered as downloadable files (PDF,
              editable DOCX, and an XLSX extraction template) within 5 working
              days of payment.
            </p>
            <p className="mt-2">
              <strong className="text-foreground">Cancellation:</strong> you
              normally have a 14-day right to cancel a digital purchase. Because
              you ask us to begin bespoke work immediately, that right ends once
              work begins — that is what the first checkbox below consents to.
              Our own guarantee is broader: if your question turns out to be
              already answered, you get a full refund and a free replacement
              guide.
            </p>
          </div>

          {/* Consents + pay */}
          <form action={startGuideCheckout}>
            <input type="hidden" name="orderId" value={order.id} />
            <input type="hidden" name="shownPence" value={displayPence} />
            <GuideConsentGate
              payLabel={
                displayPence === 0
                  ? "Confirm my free guide"
                  : `Pay ${formatPounds(displayPence)} securely with Stripe`
              }
            />
          </form>
          {displayPence > 0 && (
            <p className="text-xs text-muted-foreground">
              Payment is handled by Stripe on their secure checkout page. Your
              card details never touch Symposed&apos;s servers.
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
