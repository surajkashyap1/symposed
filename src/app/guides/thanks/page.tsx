import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { getOrderForUser } from "@/lib/queries/guides";
import { DELIVERY_PROMISE, formatPounds } from "@/lib/guides-meta";
import { isUuid } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Order confirmation — Symposed" };

export default async function GuideThanksPage({
  searchParams,
}: {
  searchParams: Promise<{ order?: string }>;
}) {
  const user = await requireUser();
  const { order: orderId } = await searchParams;
  if (!orderId || !isUuid(orderId)) notFound();

  const order = await getOrderForUser(orderId, user.id);
  if (!order) notFound();

  // The webhook, not this redirect, flips the order to paid — it can lag the
  // redirect by a few seconds (spec §3.3: users close tabs; we don't rely on
  // this page at all).
  const paid = order.status !== "submitted";

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-12">
      <Card>
        <CardHeader>
          <CardTitle>
            {paid ? "Order confirmed — we're on it" : "Finishing up…"}
          </CardTitle>
          <CardDescription>
            {paid
              ? DELIVERY_PROMISE
              : "Your payment is being confirmed. This page updates once Stripe notifies us — usually within a few seconds. If you paid, your order is safe even if you close this tab."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5 text-sm leading-relaxed">
          {paid ? (
            <>
              <p>
                Thanks, {order.fullName.split(" ")[0]}.{" "}
                {order.pricePaidPence
                  ? `We've received your payment of ${formatPounds(order.pricePaidPence)}`
                  : "Your guide is confirmed"}{" "}
                and your proforma is with the team. A person now researches
                your topic, verifies an open question, and builds your guide.{" "}
                <strong>{DELIVERY_PROMISE}</strong> You&apos;ll get an email
                with a confirmation now, and another when your guide is ready
                to download from{" "}
                <Link href="/guides/mine" className="text-primary underline">
                  My guides
                </Link>
                .
              </p>
              <div className="rounded-lg border bg-secondary/50 px-5 py-4">
                <p className="font-medium text-foreground">
                  While we work: line up your collaborators.
                </p>
                <p className="mt-1 text-muted-foreground">
                  Your guide ends with a project ready to run. Post it on the
                  Symposed board and recruit the people you&apos;ll need —
                  screeners, extractors, a statistician.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Link
                    href="/projects/new"
                    className={buttonVariants({ size: "sm" })}
                  >
                    Post your project
                  </Link>
                  <Link
                    href="/available"
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    Browse people available now
                  </Link>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Link
                href={`/guides/thanks?order=${order.id}`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                Refresh
              </Link>
              <Link
                href={`/guides/checkout?order=${order.id}`}
                className={buttonVariants({ variant: "ghost", size: "sm" })}
              >
                Back to checkout
              </Link>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
