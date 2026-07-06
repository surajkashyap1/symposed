import type { Metadata } from "next";
import Link from "next/link";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "How to use Symposed | Symposed",
  description:
    "How to find your first research project, apply well, and make the most of Symposed.",
};

// Placeholder structure — final copy to come from the founder. Keep the
// section headings; drop the copy in under each one.

export default function GuidePage() {
  return (
    <Prose
      title="How to use Symposed"
      intro="Get from signing up to your first research project."
    >
      <h2>1. Set up your profile</h2>
      <p>
        Complete your profile so listers can see who you are: your career
        stage, specialty interests, skills and availability. Verifying a
        .ac.uk or NHS email adds a verified badge that builds trust.
      </p>

      <h2>2. Find projects that fit</h2>
      <p>
        Browse <Link href="/projects">open projects</Link> and filter by
        specialty, project type and experience level. Beginner-friendly
        projects are ranked first by default — everyone starts somewhere.
      </p>

      <h2>3. Apply well</h2>
      <p>
        Applications are limited per rolling week, so make each one count:
        explain why this project, why you, and how much time you can commit.
        Ask public questions on a listing if something is unclear.
      </p>

      <h2>4. Deliver, then build your reputation</h2>
      <p>
        Once accepted, agree expectations early (role, authorship, timeline —
        see our <Link href="/research-integrity">research integrity guidelines</Link>).
        After the project, exchange reviews: they carry into every future
        application.
      </p>

      <h2>5. Posting your own project</h2>
      <p>
        Consultants, registrars and other eligible posters can{" "}
        <Link href="/projects/new">list a project</Link> after verification.
        Good listings state the work, the outputs, the time commitment and the
        authorship plan — see the{" "}
        <Link href="/posting-guidelines">posting guidelines</Link>. Never
        include patient or confidential information.
      </p>

      <p>
        Questions or stuck? <Link href="/contact">Contact us</Link> — we read
        everything.
      </p>
    </Prose>
  );
}
