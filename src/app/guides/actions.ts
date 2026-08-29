"use server";

import { randomBytes } from "node:crypto";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { guideOrders } from "@/db/schema";
import { requireUser, ensureProfile } from "@/lib/auth";
import { isUuid } from "@/lib/utils";
import {
  DATABASE_OPTIONS,
  GUIDE_GRADES,
  HOURS_OPTIONS,
  MAX_GUIDE_SPECIALTIES,
  PUBLICATION_TYPES,
  STATS_OPTIONS,
  SUPERVISOR_OPTIONS,
  TIMELINE_OPTIONS,
  TOPIC_MAX_CHARS,
} from "@/lib/guides-meta";
import {
  getPricingState,
  getOrderForUser,
  reserveCheckoutPrice,
} from "@/lib/queries/guides";
import { createCheckoutSession, stripeConfigured } from "@/lib/stripe";

function oneOf(value: string, allowed: readonly string[]): boolean {
  return allowed.includes(value);
}

// §3.2 — the proforma comes BEFORE payment, deliberately: it lets an
// administrator screen an unfulfillable request before money changes hands,
// and a five-minute investment raises checkout conversion.
export async function submitGuideProforma(formData: FormData) {
  const user = await requireUser();
  await ensureProfile(user);

  const fail = (msg: string): never =>
    redirect(`/guides/request?error=${encodeURIComponent(msg)}`);

  const fullName = String(formData.get("fullName") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const grade = String(formData.get("grade") ?? "");
  const institution = String(formData.get("institution") ?? "").trim();
  const topics = String(formData.get("topics") ?? "").trim();
  const publicationType = String(formData.get("publicationType") ?? "");
  const hoursPerWeek = String(formData.get("hoursPerWeek") ?? "");
  const timeline = String(formData.get("timeline") ?? "");
  const statsConfidence = String(formData.get("statsConfidence") ?? "");
  const supervisor = String(formData.get("supervisor") ?? "");
  const specialtyUndecided = formData.get("specialtyUndecided") === "on";

  const specialties = String(formData.get("specialties") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, MAX_GUIDE_SPECIALTIES);

  const databases = formData
    .getAll("databases")
    .map(String)
    .filter((d) => oneOf(d, DATABASE_OPTIONS));

  if (!fullName || !email.includes("@") || !institution)
    fail("Please complete your name, email and institution.");
  if (!oneOf(grade, GUIDE_GRADES)) fail("Please choose your grade or role.");
  if (specialties.length === 0 && !specialtyUndecided)
    fail("Give up to 3 specialty interests, or tick undecided.");
  if (!topics) fail("Tell us about your topic areas of interest.");
  if (topics.length > TOPIC_MAX_CHARS)
    fail(`Topic areas are capped at ${TOPIC_MAX_CHARS} characters.`);
  if (!oneOf(publicationType, PUBLICATION_TYPES))
    fail("Please choose the type of publication you want.");
  if (!oneOf(hoursPerWeek, HOURS_OPTIONS))
    fail("Please say how many hours you have per week.");
  if (!oneOf(timeline, TIMELINE_OPTIONS)) fail("Please choose a timeline.");
  if (!oneOf(statsConfidence, STATS_OPTIONS))
    fail("Please rate your statistical confidence.");
  if (!oneOf(supervisor, SUPERVISOR_OPTIONS))
    fail("Please say whether you have a supervisor.");
  if (databases.length === 0)
    fail("Pick at least one database access option (or 'Unsure').");

  const collaboratorsRaw = String(formData.get("collaborators") ?? "").trim();
  const proforma = {
    grade,
    institution,
    specialties: specialtyUndecided ? ["Undecided"] : specialties,
    specialtyUndecided,
    topics,
    publicationType,
    existingTitle: String(formData.get("existingTitle") ?? "").trim() || null,
    hoursPerWeek,
    timeline,
    statsConfidence,
    databases,
    supervisor,
    collaborators: collaboratorsRaw ? Number.parseInt(collaboratorsRaw, 10) : null,
    anythingElse: String(formData.get("anythingElse") ?? "").trim() || null,
  };

  // Retain proforma data across abandoned checkouts (spec §3.3): one open
  // 'submitted' order per user is reused rather than duplicated.
  const [existing] = await db
    .select({ id: guideOrders.id })
    .from(guideOrders)
    .where(
      and(eq(guideOrders.profileId, user.id), eq(guideOrders.status, "submitted"))
    )
    .orderBy(desc(guideOrders.createdAt))
    .limit(1);

  let orderId: string;
  if (existing) {
    await db
      .update(guideOrders)
      .set({
        proforma: JSON.stringify(proforma),
        fullName,
        email,
        updatedAt: new Date(),
      })
      .where(eq(guideOrders.id, existing.id));
    orderId = existing.id;
  } else {
    const [created] = await db
      .insert(guideOrders)
      .values({
        profileId: user.id,
        proforma: JSON.stringify(proforma),
        fullName,
        email,
        reviewToken: randomBytes(24).toString("base64url"),
      })
      .returning({ id: guideOrders.id });
    orderId = created.id;
  }

  redirect(`/guides/checkout?order=${orderId}`);
}

// §3.2 consent block + §3.3 payment. The price is resolved server-side under
// a row lock at this moment; if it differs from the price the user was shown,
// we bounce back for explicit confirmation before charging (spec §3.1.3).
export async function startGuideCheckout(formData: FormData) {
  const user = await requireUser();
  const profile = await ensureProfile(user);

  const orderId = String(formData.get("orderId") ?? "");
  if (!isUuid(orderId)) redirect("/guides");
  const back = `/guides/checkout?order=${orderId}`;
  const fail = (qs: string): never => redirect(`${back}&${qs}`);

  const order = await getOrderForUser(orderId, user.id);
  if (!order) redirect("/guides");
  if (order.status !== "submitted") redirect(`/guides/thanks?order=${orderId}`);

  // Both consents must be actively ticked (server-enforced; never pre-ticked).
  if (
    formData.get("consentImmediate") !== "on" ||
    formData.get("consentTerms") !== "on"
  )
    fail("error=" + encodeURIComponent("Please tick both consent boxes to continue."));

  const hdrs = await headers();
  const ip =
    hdrs.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    hdrs.get("x-real-ip") ??
    null;
  const ipCountry = hdrs.get("x-vercel-ip-country") ?? null;

  // Country allow-list (spec §7.6–7.8): blocked markets get a polite message,
  // not a broken checkout.
  const pricing = await getPricingState();
  if (ipCountry && pricing.blockedCountries.includes(ipCountry))
    fail("blocked=1");

  if (!stripeConfigured())
    fail(
      "error=" +
        encodeURIComponent(
          "Payments aren't switched on yet. Please try again soon."
        )
    );

  // Record consent evidence before charging (spec §3.2: without it the
  // cancellation waiver is worthless).
  const now = new Date();
  await db
    .update(guideOrders)
    .set({
      consentImmediateAt: now,
      consentTermsAt: now,
      consentIp: ip,
      ipCountry,
      updatedAt: now,
    })
    .where(eq(guideOrders.id, orderId));

  // Race-safe server-side price resolution.
  const { amountPence } = await reserveCheckoutPrice(orderId);

  // If the price moved while the page was open, confirm before charging.
  const shownPence = Number.parseInt(String(formData.get("shownPence") ?? ""), 10);
  if (!Number.isNaN(shownPence) && shownPence !== amountPence)
    fail(`priceChanged=${amountPence}`);

  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  let sessionUrl: string;
  try {
    const session = await createCheckoutSession({
      orderId,
      amountPence,
      productName: "Symposed Publication Guide (bespoke, human-verified)",
      customerEmail: order.email || profile.email,
      successUrl: `${base}/guides/thanks?order=${orderId}`,
      cancelUrl: `${base}/guides/checkout?order=${orderId}`,
    });
    await db
      .update(guideOrders)
      .set({ stripeSessionId: session.id, updatedAt: new Date() })
      .where(eq(guideOrders.id, orderId));
    sessionUrl = session.url;
  } catch {
    fail(
      "error=" +
        encodeURIComponent("Could not start checkout. Nothing has been charged — please try again.")
    );
  }

  redirect(sessionUrl!);
}
