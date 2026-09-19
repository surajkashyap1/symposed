import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders } from "@/db/schema";
import { sendEmail } from "@/lib/email";
import { DELIVERY_PROMISE, formatPounds } from "@/lib/guides-meta";
import { getPaymentCardCountry, verifyStripeSignature } from "@/lib/stripe";

// Stripe webhook — the ONLY place an order becomes paid (spec §3.3: users
// close tabs; the browser redirect is never trusted). Idempotent: Stripe
// retries, and a duplicate delivery must not double-process. Idempotency is
// the guarded UPDATE below — only the delivery that transitions
// submitted -> paid sends emails; retries match zero rows and no-op.
export const dynamic = "force-dynamic";

type CheckoutSessionEvent = {
  type: string;
  data: {
    object: {
      id: string;
      payment_status?: string;
      payment_intent?: string | null;
      amount_total?: number | null;
      customer_details?: { address?: { country?: string | null } | null } | null;
      metadata?: { order_id?: string } | null;
    };
  };
};

export async function POST(request: Request) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!secret) {
    return NextResponse.json({ error: "webhook not configured" }, { status: 500 });
  }

  const payload = await request.text();
  const signature = request.headers.get("stripe-signature");
  if (!verifyStripeSignature(payload, signature, secret)) {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }

  const event = JSON.parse(payload) as CheckoutSessionEvent;
  if (event.type !== "checkout.session.completed") {
    return NextResponse.json({ received: true });
  }

  const session = event.data.object;
  if (session.payment_status && session.payment_status !== "paid") {
    // Async payment methods would arrive later; card payments are 'paid' here.
    return NextResponse.json({ received: true });
  }

  const orderId = session.metadata?.order_id ?? null;
  const billingCountry = session.customer_details?.address?.country ?? null;
  const paymentIntentId =
    typeof session.payment_intent === "string" ? session.payment_intent : null;

  // Card issuing country — best-effort location evidence (spec §7.6).
  const cardCountry = paymentIntentId
    ? await getPaymentCardCountry(paymentIntentId)
    : null;

  // Idempotency: only the transition submitted -> paid matches; a retried
  // delivery updates zero rows and sends nothing.
  const updated = await db
    .update(guideOrders)
    .set({
      status: "paid",
      paidAt: new Date(),
      pricePaidPence: session.amount_total ?? null,
      stripePaymentIntentId: paymentIntentId,
      billingCountry,
      cardCountry,
      updatedAt: new Date(),
    })
    .where(
      and(
        eq(guideOrders.stripeSessionId, session.id),
        eq(guideOrders.status, "submitted"),
        ...(orderId ? [eq(guideOrders.id, orderId)] : [])
      )
    )
    .returning();

  if (updated.length === 0) {
    // Already processed (retry) or unknown session — acknowledge either way.
    return NextResponse.json({ received: true, duplicate: true });
  }

  const order = updated[0];

  // Country mismatch flag for admin review (spec §7.6).
  const countries = [order.ipCountry, order.billingCountry, order.cardCountry]
    .filter((c): c is string => Boolean(c));
  const mismatch = new Set(countries).size > 1;
  if (mismatch) {
    await db
      .update(guideOrders)
      .set({ countryMismatch: true })
      .where(eq(guideOrders.id, order.id));
  }

  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  await sendEmail({
    to: order.email,
    subject: "Symposed: payment received, your guide is underway",
    text: [
      `Hi ${order.fullName},`,
      "",
      `Thanks, we've received your payment of ${formatPounds(order.pricePaidPence ?? order.priceAtCheckoutPence ?? 0)} for a Symposed Publication Guide. This email is your receipt.`,
      "",
      `${DELIVERY_PROMISE} We now research your topic using our own developed and tested approach, verify that your question is genuinely open, and build the guide around it. It will appear in "My guides" (${base}/guides/mine) and we'll email you the moment it's ready.`,
      "",
      "While you wait: your guide ends with a project ready to run. You can already post it on Symposed to recruit collaborators:",
      `${base}/projects/new`,
      "",
      "Our commitment: if you believe the question in your guide has already been published, contact us within 30 days with the citation and we will refine the title, the angle and the workflow and issue you a modified guide at no cost. This does not affect your statutory rights.",
    ].join("\n"),
  });

  // Admin heads-up so the 7-working-day clock starts consciously.
  const inbox =
    process.env.CONTACT_INBOX ??
    (process.env.ADMIN_EMAILS ?? "").split(",")[0]?.trim();
  if (inbox) {
    await sendEmail({
      to: inbox,
      subject: `Guide order paid: ${order.fullName} (${formatPounds(order.pricePaidPence ?? 0)})`,
      text: `Order ${order.id} is paid${order.discountApplied ? " (discounted price)" : ""}. The 7-working-day delivery clock is running.\n\n${base}/admin`,
    });
  }

  return NextResponse.json({ received: true });
}
