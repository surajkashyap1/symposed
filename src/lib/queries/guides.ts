import { and, desc, eq, gt, or, sql } from "drizzle-orm";
import { db } from "@/db";
import { guideOrderFiles, guideOrders, guidePricingConfig, guideReviews } from "@/db/schema";

// How long a started checkout holds a discount slot. Matches the Stripe
// session expiry (30 min) plus slack for webhook lag.
export const CHECKOUT_RESERVATION_MINUTES = 35;

export type PricingState = {
  standardPricePence: number;
  introPricePence: number;
  introQuantity: number;
  // Guide sales are open. While off, checkout is refused: nothing is ever
  // given away free (Samarth, 2026-11-17: the free allocation has ended).
  paymentsEnabled: boolean;
  // Public counter: decrements on a COMPLETED, charged request only, never on
  // form submission (amendment §2). `paidCount` is the ladder position.
  paidCount: number;
  introRemainingPublic: number;
  // The price the NEXT guide would cost given the current ladder position.
  currentPricePence: number;
  blockedCountries: string[];
};

// The price for the guide at ladder position `position` (0-indexed, counting
// charged guides only): the intro tier for the first `introQuantity`, then
// standard. The free band ended on 2026-11-17 (Samarth): guides given free
// before then do not use up intro places, and `free_quantity` is no longer read.
export function priceForPosition(
  cfg: {
    introQuantity: number;
    introPricePence: number;
    standardPricePence: number;
  },
  position: number
): number {
  if (position < cfg.introQuantity) return cfg.introPricePence;
  return cfg.standardPricePence;
}

// A guide that was given free (before charging began) holds no ladder place.
const CHARGED = sql`coalesce(${guideOrders.pricePaidPence}, ${guideOrders.priceAtCheckoutPence}, 1) > 0`;

export async function getPricingState(): Promise<PricingState> {
  const [cfg] = await db.select().from(guidePricingConfig).limit(1);
  if (!cfg) throw new Error("guide_pricing_config row missing, run drizzle/manual/0006_guides_seed.sql");

  // A guide "consumes" a ladder slot once its request is completed (paid
  // family) and it was charged for.
  const [{ paidCount }] = await db
    .select({ paidCount: sql<number>`count(*)::int` })
    .from(guideOrders)
    .where(
      and(sql`${guideOrders.status} in ('paid', 'in_progress', 'delivered')`, CHARGED)
    );

  const introRemainingPublic = Math.max(0, cfg.introQuantity - paidCount);

  return {
    standardPricePence: cfg.standardPricePence,
    introPricePence: cfg.introPricePence,
    introQuantity: cfg.introQuantity,
    paymentsEnabled: cfg.paymentsEnabled,
    paidCount,
    introRemainingPublic,
    currentPricePence: priceForPosition(cfg, paidCount),
    blockedCountries: cfg.blockedCountries,
  };
}

// Race-safe price resolution at the moment checkout starts (spec §3.1.3).
// Runs in a transaction holding a row lock on the config row, so two
// simultaneous checkouts with one slot left serialise: exactly one reserves
// the discount. Paid orders hold their slot forever; a started-but-unpaid
// checkout holds it only while its Stripe session can still complete.
export async function reserveCheckoutPrice(orderId: string): Promise<{
  amountPence: number;
  discountApplied: boolean;
}> {
  return db.transaction(async (tx) => {
    const [cfg] = await tx
      .select()
      .from(guidePricingConfig)
      .for("update");
    if (!cfg) throw new Error("pricing config missing");

    // Ladder position = every OTHER charged order that is holding a slot: paid
    // family orders (which hold forever) plus started-but-unpaid checkouts
    // whose Stripe session can still complete.
    const [{ held }] = await tx
      .select({ held: sql<number>`count(*)::int` })
      .from(guideOrders)
      .where(
        and(
          sql`${guideOrders.id} <> ${orderId}`,
          CHARGED,
          or(
            sql`${guideOrders.status} in ('paid', 'in_progress', 'delivered')`,
            and(
              eq(guideOrders.status, "submitted"),
              gt(
                guideOrders.checkoutStartedAt,
                sql`now() - make_interval(mins => ${CHECKOUT_RESERVATION_MINUTES})`
              )
            )
          )
        )
      );

    const amountPence = priceForPosition(cfg, held);
    // "Discounted" means the below-standard intro band, used for the admin
    // badge and the paid-confirmation email.
    const discountApplied = amountPence < cfg.standardPricePence;

    await tx
      .update(guideOrders)
      .set({
        discountApplied,
        priceAtCheckoutPence: amountPence,
        checkoutStartedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(guideOrders.id, orderId));

    return { amountPence, discountApplied };
  });
}

export async function getOrderForUser(orderId: string, profileId: string) {
  const [row] = await db
    .select()
    .from(guideOrders)
    .where(and(eq(guideOrders.id, orderId), eq(guideOrders.profileId, profileId)))
    .limit(1);
  return row ?? null;
}

export async function listOrdersForUser(profileId: string) {
  return db
    .select()
    .from(guideOrders)
    .where(eq(guideOrders.profileId, profileId))
    .orderBy(desc(guideOrders.createdAt));
}

export async function listOrderFiles(orderId: string) {
  return db
    .select()
    .from(guideOrderFiles)
    .where(eq(guideOrderFiles.orderId, orderId))
    .orderBy(guideOrderFiles.createdAt);
}

// Approved reviews for /guides. Aggregate only once there are >= 3 (spec §3.5).
export async function getPublishedGuideReviews() {
  const reviews = await db
    .select()
    .from(guideReviews)
    .where(eq(guideReviews.status, "approved"))
    .orderBy(desc(guideReviews.publishedAt));

  const average =
    reviews.length >= 3
      ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length
      : null;

  return { reviews, average };
}

export async function getOrderByReviewToken(token: string) {
  const [row] = await db
    .select()
    .from(guideOrders)
    .where(eq(guideOrders.reviewToken, token))
    .limit(1);
  return row ?? null;
}
