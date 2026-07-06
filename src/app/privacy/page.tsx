import type { Metadata } from "next";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "Privacy Policy | Symposed",
  description: "How Symposed collects, uses, and protects your personal data.",
};

export default function PrivacyPage() {
  return (
    <Prose title="Privacy Policy" updated="June 2026">
      <p>
        Symposed (&ldquo;we&rdquo;) is a UK-based platform connecting students and
        healthcare professionals with research opportunities. This policy explains
        what personal data we process and why, under the UK GDPR and the Data
        Protection Act 2018. We are the data controller for the information
        described here.
      </p>
      <p>
        <strong>This is a template and must be reviewed by a qualified
        professional before launch.</strong>
      </p>

      <h2>Data we collect</h2>
      <ul>
        <li>
          <strong>Account &amp; profile:</strong> name, email address, institution,
          career stage, specialty, summary, skills, availability, and verification
          status.
        </li>
        <li>
          <strong>Activity:</strong> projects you post, applications you submit,
          messages you send, questions, reviews, and badges.
        </li>
        <li>
          <strong>Technical:</strong> essential cookies for authentication and
          basic logs needed to run and secure the service.
        </li>
      </ul>

      <h2>How we use it</h2>
      <ul>
        <li>To operate the marketplace, matching applicants and listers.</li>
        <li>To verify eligibility (e.g. institutional email) and prevent abuse.</li>
        <li>To send service notifications about your applications and messages.</li>
        <li>To understand aggregate usage and improve the platform.</li>
      </ul>
      <p>
        Our lawful bases are performance of a contract (providing the service) and
        our legitimate interests in running a trustworthy platform. We do not sell
        your data.
      </p>

      <h2>Storage &amp; processors</h2>
      <p>
        Data is stored with Supabase (Postgres, Auth, Storage) hosted in the
        EU/London region, and the application is hosted on Vercel. Email, when
        enabled, is sent via Resend. These providers process data on our behalf
        under data-processing agreements.
      </p>

      <h2>Retention</h2>
      <p>
        We keep your data while your account is active. You can delete your account
        at any time, which removes your profile and associated content. Some
        records may be retained where required by law.
      </p>

      <h2>Your rights</h2>
      <p>
        You have the right to access, correct, delete, restrict, or port your data,
        and to object to processing. To exercise these rights, contact us. You can
        also complain to the UK Information Commissioner&rsquo;s Office (ICO).
      </p>

      <h2>Contact</h2>
      <p>
        For privacy queries, email the address listed on our contact channels. See
        also our <a href="/terms">Terms of Use</a> and{" "}
        <a href="/ethos">Ethos &amp; usage policy</a>.
      </p>
    </Prose>
  );
}
