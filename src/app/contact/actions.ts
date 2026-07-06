"use server";

import { redirect } from "next/navigation";
import { db } from "@/db";
import { contactMessages } from "@/db/schema";
import { getSessionUser } from "@/lib/auth";
import { sendEmail } from "@/lib/email";

const TOPICS = new Set([
  "feedback",
  "complaint",
  "abuse or safety",
  "data protection",
  "other",
]);

const MAX_MESSAGE_CHARS = 5000;

// Contact form: works logged in or out. Stored for /admin and forwarded by
// email when Resend is configured. Also the entry point for data protection
// complaints (Data Protection Complaints Procedure §2).
export async function submitContactMessage(formData: FormData) {
  const user = await getSessionUser();
  const topicRaw = String(formData.get("topic") ?? "").trim().toLowerCase();
  const topic = TOPICS.has(topicRaw) ? topicRaw : "other";
  const email =
    String(formData.get("email") ?? "").trim().toLowerCase() ||
    user?.email ||
    null;
  const message = String(formData.get("message") ?? "").trim();

  if (!message)
    redirect(`/contact?error=${encodeURIComponent("Please write a message.")}`);

  await db.insert(contactMessages).values({
    senderId: user?.id ?? null,
    email,
    topic,
    message: message.slice(0, MAX_MESSAGE_CHARS),
  });

  // Best-effort forward so urgent topics aren't only discovered on /admin.
  await sendEmail({
    to: topic === "data protection" ? "privacy@symposed.org" : "hello@symposed.org",
    subject: `Symposed contact form: ${topic}`,
    text: `From: ${email ?? "not given"}\nTopic: ${topic}\n\n${message}`,
  });

  redirect("/contact?sent=1");
}
