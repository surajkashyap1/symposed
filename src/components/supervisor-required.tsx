import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

// Shown to logged-in users who aren't verified when they reach a page that
// posts/edits projects. Posting is gated to verified accounts (an academic or
// health-service email, confirmed at signup or via the "Get verified" flow).
export function SupervisorRequired() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <Card>
        <CardHeader>
          <CardTitle>Verify your account to post</CardTitle>
          <CardDescription>
            Posting a project requires a verified account. Verify with a
            university or health-service email (e.g. <strong>.edu</strong>,{" "}
            <strong>.ac.uk</strong>, <strong>.nhs.uk</strong>), you can use a
            different address from the one you signed up with. No institutional
            email? Contact us and we&apos;ll verify you manually.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Link href="/onboarding#verify" className={buttonVariants()}>
            Get verified
          </Link>
          <Link
            href="/projects"
            className={buttonVariants({ variant: "outline" })}
          >
            Browse projects
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
