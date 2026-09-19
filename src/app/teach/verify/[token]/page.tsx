import { notFound } from "next/navigation";
import { getSubmissionByClinicianToken } from "@/lib/queries/teaching";
import { respondToClinicianRequest } from "@/app/teach/actions";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata = { title: "Confirm review | Symposed" };

// Reached from the email sent to the named approving clinician. No login —
// the single-use token is the identity (spec §4.2).
export default async function ClinicianVerifyPage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ done?: string }>;
}) {
  const [{ token }, { done }] = await Promise.all([params, searchParams]);
  const submission = await getSubmissionByClinicianToken(token);
  if (!submission) notFound();

  const answered = submission.clinicianStatus !== "pending";

  return (
    <main className="mx-auto w-full max-w-xl flex-1 px-6 py-16">
      <Card>
        <CardHeader>
          <CardTitle>Course review confirmation</CardTitle>
          <CardDescription>
            You&apos;ve been named as the approving clinician for a proposed
            Symposed teaching course.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Course</dt>
              <dd className="mt-0.5 font-medium">{submission.title}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Format</dt>
              <dd className="mt-0.5 font-medium">{submission.sessionsPlan}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Named clinician</dt>
              <dd className="mt-0.5 font-medium">
                {submission.clinicianName}, {submission.clinicianGrade},{" "}
                {submission.clinicianSpecialty},{" "}
                {submission.clinicianInstitution}
              </dd>
            </div>
          </dl>

          {answered ? (
            <p
              className={`mt-6 rounded-md border px-4 py-3 text-sm ${
                submission.clinicianStatus === "confirmed"
                  ? "border-success/30 bg-success/10"
                  : "border-destructive/30 bg-destructive/10"
              }`}
            >
              {done
                ? "Thank you, your response has been recorded."
                : `This request has already been ${
                    submission.clinicianStatus === "confirmed"
                      ? "confirmed"
                      : "declined"
                  }.`}{" "}
              You can close this page.
            </p>
          ) : (
            <>
              <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
                By confirming, you agree to review this course&apos;s material
                for clinical accuracy and safety before it is published. If you
                haven&apos;t agreed to this or don&apos;t recognise the
                proposer, please decline.
              </p>
              <div className="mt-5 flex gap-3">
                <form action={respondToClinicianRequest}>
                  <input type="hidden" name="token" value={token} />
                  <input type="hidden" name="decision" value="confirm" />
                  <Button type="submit">Confirm, I&apos;ll review it</Button>
                </form>
                <form action={respondToClinicianRequest}>
                  <input type="hidden" name="token" value={token} />
                  <input type="hidden" name="decision" value="decline" />
                  <Button type="submit" variant="outline">
                    Decline
                  </Button>
                </form>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
