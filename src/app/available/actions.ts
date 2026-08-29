"use server";

import { redirect } from "next/navigation";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { availabilityListings, listingContacts, notifications } from "@/db/schema";
import { requireUser, ensureProfile, getProfile } from "@/lib/auth";
import { sendEmail } from "@/lib/email";
import { isUuid } from "@/lib/utils";
import { CAREER_STAGES } from "@/lib/profile";
import {
  CONTACT_MAX_CHARS,
  CONTACTS_PER_DAY,
  HEADLINE_MAX_CHARS,
  LOOKING_FOR_MAX_CHARS,
  MAX_LISTING_SPECIALTIES,
  SKILLS_OFFERED_SET,
  listingExpiryDate,
} from "@/lib/board-meta";
import { countRecentContacts, getLiveListing } from "@/lib/queries/availability";

function fail(path: string, message: string): never {
  redirect(`${path}?error=${encodeURIComponent(message)}`);
}

// Create or replace the caller's listing (one per user, spec §5.3).
// Saving always resets the 60-day clock and republishes a removed/expired
// listing — "editing replaces the existing one".
export async function upsertListing(formData: FormData) {
  const user = await requireUser();
  await ensureProfile(user);

  const headline = String(formData.get("headline") ?? "").trim();
  const lookingFor = String(formData.get("lookingFor") ?? "").trim();
  const region = String(formData.get("region") ?? "").trim() || null;
  const previousPublications =
    String(formData.get("previousPublications") ?? "").trim() || null;
  const displayInitialsOnly = formData.get("displayInitialsOnly") === "on";
  const showInstitution = formData.get("showInstitution") === "on";

  const specialties = String(formData.get("specialties") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, MAX_LISTING_SPECIALTIES)
    .join(", ") || null;

  const skills = formData
    .getAll("skills")
    .map(String)
    .filter((s) => SKILLS_OFFERED_SET.has(s));

  const hoursRaw = String(formData.get("hoursPerWeek") ?? "").trim();
  const hoursPerWeek = hoursRaw ? Number.parseInt(hoursRaw, 10) : null;
  const availableFromRaw = String(formData.get("availableFrom") ?? "").trim();
  const availableFrom = /^\d{4}-\d{2}-\d{2}$/.test(availableFromRaw)
    ? availableFromRaw
    : null;

  if (!headline) fail("/available/new", "Please write a headline.");
  if (headline.length > HEADLINE_MAX_CHARS)
    fail("/available/new", `Headline must be ${HEADLINE_MAX_CHARS} characters or fewer.`);
  if (!lookingFor) fail("/available/new", "Please say what you're looking for.");
  if (lookingFor.length > LOOKING_FOR_MAX_CHARS)
    fail(
      "/available/new",
      `"What I am looking for" must be ${LOOKING_FOR_MAX_CHARS} characters or fewer.`
    );
  if (skills.length === 0)
    fail("/available/new", "Pick at least one skill you can offer.");
  if (hoursPerWeek != null && (Number.isNaN(hoursPerWeek) || hoursPerWeek < 0 || hoursPerWeek > 80))
    fail("/available/new", "Hours per week must be between 0 and 80.");

  const values = {
    headline,
    lookingFor,
    region,
    specialties,
    skills,
    hoursPerWeek,
    availableFrom,
    previousPublications,
    displayInitialsOnly,
    showInstitution,
    status: "active" as const,
    expiresAt: listingExpiryDate(),
    foundProjectAt: null,
    renewalEmailedAt: null,
    updatedAt: new Date(),
  };

  await db
    .insert(availabilityListings)
    .values({ profileId: user.id, ...values })
    .onConflictDoUpdate({
      target: availabilityListings.profileId,
      set: values,
    });

  redirect("/available?posted=1");
}

// One-click renewal: resets the clock and bumps the listing to the top.
export async function renewListing() {
  const user = await requireUser();
  await db
    .update(availabilityListings)
    .set({
      status: "active",
      expiresAt: listingExpiryDate(),
      renewalEmailedAt: null,
      foundProjectAt: null,
      updatedAt: new Date(),
    })
    .where(eq(availabilityListings.profileId, user.id));
  redirect("/available?renewed=1");
}

// Outcome tracking (spec §5.3): the metric that says the board works.
export async function markListingFound() {
  const user = await requireUser();
  await db
    .update(availabilityListings)
    .set({
      status: "found_project",
      foundProjectAt: new Date(),
      updatedAt: new Date(),
    })
    .where(
      and(
        eq(availabilityListings.profileId, user.id),
        eq(availabilityListings.status, "active")
      )
    );
  redirect("/available?found=1");
}

// Take the listing off the board without recording an outcome.
export async function removeListing() {
  const user = await requireUser();
  await db
    .update(availabilityListings)
    .set({ status: "removed", updatedAt: new Date() })
    .where(eq(availabilityListings.profileId, user.id));
  redirect("/available?removed=1");
}

// The contact relay (spec §5.2): sender must be signed in, the owner's email
// is never exposed, both sides are logged, and outbound volume is capped.
export async function sendListingContact(formData: FormData) {
  const user = await requireUser();
  const profile = await ensureProfile(user);

  const listingId = String(formData.get("listingId") ?? "");
  if (!isUuid(listingId)) redirect("/available");
  const contactPath = `/available/${listingId}/contact`;

  const body = String(formData.get("body") ?? "").trim();
  if (!body) fail(contactPath, "Please write a message.");
  if (body.length > CONTACT_MAX_CHARS)
    fail(contactPath, `Messages are capped at ${CONTACT_MAX_CHARS} characters.`);

  const listing = await getLiveListing(listingId);
  if (!listing) redirect("/available");
  if (listing.profileId === user.id)
    fail(contactPath, "This is your own listing.");

  const sentToday = await countRecentContacts(user.id);
  if (sentToday >= CONTACTS_PER_DAY)
    fail(
      contactPath,
      `You've reached the limit of ${CONTACTS_PER_DAY} messages in 24 hours. Try again tomorrow.`
    );

  await db.insert(listingContacts).values({
    listingId,
    senderId: user.id,
    recipientId: listing.profileId,
    body,
  });

  // In-app notification (inserted directly — the email below is the full
  // relay with reply-to, so notify()'s generic email would double-send).
  await db.insert(notifications).values({
    profileId: listing.profileId,
    type: "message",
    title: "Someone got in touch about your availability listing",
    body: `${profile.fullName} replied to your "Available for projects" listing.`,
    link: `/profile/${user.id}`,
  });

  const owner = await getProfile(listing.profileId);
  const stage =
    CAREER_STAGES.find((s) => s.value === profile.careerStage)?.label ?? null;
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "";
  if (owner?.email)
    await sendEmail({
      to: owner.email,
      subject: `Symposed: ${profile.fullName} is interested in working with you`,
      text: [
        `${profile.fullName} saw your "Available for projects" listing on Symposed and sent you a message:`,
        "",
        body,
        "",
        "---",
        `About the sender:`,
        `Name: ${profile.fullName}`,
        stage ? `Role: ${stage}` : null,
        profile.university ? `Institution: ${profile.university}` : null,
        `Profile: ${base}/profile/${user.id}`,
        "",
        "Reply to this email to respond directly.",
      ]
        .filter((l) => l != null)
        .join("\n"),
      replyTo: profile.email,
    });

  redirect(`/available/${listingId}/contact?sent=1`);
}
