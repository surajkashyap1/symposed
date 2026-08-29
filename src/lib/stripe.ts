import { createHmac, timingSafeEqual } from "node:crypto";

// Plain-fetch Stripe client — same zero-SDK convention as email.ts. Only the
// three calls this build needs; card details never touch our servers (hosted
// Stripe Checkout only).

const STRIPE_API = "https://api.stripe.com/v1";

export function stripeConfigured(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY);
}

function authHeaders() {
  return {
    Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}`,
    "Content-Type": "application/x-www-form-urlencoded",
  };
}

export type CheckoutSession = {
  id: string;
  url: string;
};

// Hosted Checkout session. The price is resolved server-side by the caller —
// never taken from the client (spec §3.3). The session expires after 30
// minutes so an abandoned checkout releases its discount reservation.
export async function createCheckoutSession(input: {
  orderId: string;
  amountPence: number;
  productName: string;
  customerEmail: string;
  successUrl: string;
  cancelUrl: string;
}): Promise<CheckoutSession> {
  const params = new URLSearchParams({
    mode: "payment",
    "line_items[0][price_data][currency]": "gbp",
    "line_items[0][price_data][unit_amount]": String(input.amountPence),
    "line_items[0][price_data][product_data][name]": input.productName,
    "line_items[0][quantity]": "1",
    customer_email: input.customerEmail,
    client_reference_id: input.orderId,
    "metadata[order_id]": input.orderId,
    "payment_intent_data[metadata][order_id]": input.orderId,
    success_url: input.successUrl,
    cancel_url: input.cancelUrl,
    expires_at: String(Math.floor(Date.now() / 1000) + 30 * 60),
    billing_address_collection: "required",
  });

  const res = await fetch(`${STRIPE_API}/checkout/sessions`, {
    method: "POST",
    headers: authHeaders(),
    body: params,
  });
  if (!res.ok) {
    const detail = await res.text();
    console.error("Stripe session creation failed", res.status, detail);
    throw new Error("Could not start checkout.");
  }
  const session = (await res.json()) as { id: string; url: string };
  return { id: session.id, url: session.url };
}

// Charge details for location evidence (spec §7.6): billing country comes on
// the session; the card issuing country needs the payment intent's charge.
export async function getPaymentCardCountry(
  paymentIntentId: string
): Promise<string | null> {
  const res = await fetch(
    `${STRIPE_API}/payment_intents/${paymentIntentId}?expand[]=latest_charge`,
    { headers: authHeaders() }
  );
  if (!res.ok) return null;
  const intent = (await res.json()) as {
    latest_charge?: {
      payment_method_details?: { card?: { country?: string | null } };
    };
  };
  return intent.latest_charge?.payment_method_details?.card?.country ?? null;
}

// Webhook signature verification (Stripe scheme: HMAC-SHA256 over
// "<timestamp>.<payload>" with the endpoint secret).
export function verifyStripeSignature(
  payload: string,
  signatureHeader: string | null,
  secret: string,
  toleranceSeconds = 300
): boolean {
  if (!signatureHeader) return false;
  const parts = new Map<string, string[]>();
  for (const kv of signatureHeader.split(",")) {
    const [k, v] = kv.split("=", 2);
    if (!k || !v) continue;
    const list = parts.get(k.trim()) ?? [];
    list.push(v.trim());
    parts.set(k.trim(), list);
  }
  const timestamp = Number(parts.get("t")?.[0]);
  const signatures = parts.get("v1") ?? [];
  if (!timestamp || signatures.length === 0) return false;
  if (Math.abs(Date.now() / 1000 - timestamp) > toleranceSeconds) return false;

  const expected = createHmac("sha256", secret)
    .update(`${timestamp}.${payload}`)
    .digest("hex");
  const expectedBuf = Buffer.from(expected);
  return signatures.some((sig) => {
    const sigBuf = Buffer.from(sig);
    return (
      sigBuf.length === expectedBuf.length && timingSafeEqual(sigBuf, expectedBuf)
    );
  });
}
