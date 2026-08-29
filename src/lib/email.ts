// Plain-fetch email sender, gated on Resend being configured (same pattern as
// notify.ts). Returns true only if an email was actually dispatched, so callers
// can fall back to showing a manual link while the zero-budget setup has no
// email provider. "Just turns on" once RESEND_API_KEY + RESEND_FROM are set.
export async function sendEmail(input: {
  to: string;
  subject: string;
  text: string;
  // Relay pattern (e.g. the availability board): replies go to the person
  // who wrote the message, not to the platform address.
  replyTo?: string;
}): Promise<boolean> {
  const apiKey = process.env.RESEND_API_KEY;
  const from = process.env.RESEND_FROM;
  if (!apiKey || !from) return false;

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: input.to,
        subject: input.subject,
        text: input.text,
        ...(input.replyTo ? { reply_to: input.replyTo } : {}),
      }),
    });
    return res.ok;
  } catch (e) {
    console.error("sendEmail failed", e);
    return false;
  }
}
