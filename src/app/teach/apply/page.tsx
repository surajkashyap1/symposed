import { redirect } from "next/navigation";

// Amendment §10 — the teaching feature is in development. The full submission
// proforma (including the file upload and the approving-clinician block) is
// removed for now; the public /teach page is a short description plus an email
// capture. Any direct hit on the old apply URL goes there.
export default function TeachApplyPage() {
  redirect("/teach");
}
