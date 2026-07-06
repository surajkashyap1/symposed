import type { Metadata } from "next";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "Ethos and Usage Policy | Symposed",
  description:
    "How we build trust, prevent spam, and keep Symposed welcoming to beginners.",
};

export default function EthosPage() {
  return (
    <Prose
      title="Ethos & usage policy"
      intro="The principles that keep Symposed fair, trustworthy and welcoming."
    >
      <p>
        This platform is free to use for everyone. By using Symposed you agree to
        take part in good faith. Apply to projects you genuinely intend to
        complete, communicate honestly, and treat collaborators and supervisors
        with respect.
      </p>

      <h2>Creating trust and preventing spam</h2>
      <p>
        We want to avoid situations where everyone applies to every project, which
        reduces the quality of applications and increases ghosting. Commitment to a
        project is essential to seeing it through, as they take significant time and
        effort. So we want you to apply to projects you find interesting, that are
        useful for your future career, and that you can realistically see yourself
        completing.
      </p>
      <p>
        For this reason we limit how many applications you can send in a rolling
        period (the current limit is shown when you apply). This prevents high
        volumes of low-quality applications and ghosting, and may change over time
        based on how users feel. If you post a research opportunity with a
        validated supervisor, you can earn extra applications.
      </p>

      <h2>Reviews and reputation</h2>
      <p>
        To build trust in the platform and in yourself, you receive reviews of your
        work on projects, shown on your profile, which you can use in future
        applications. People posting opportunities use these to judge
        trustworthiness and commitment. It is your responsibility to ask
        collaborators and supervisors for reviews.
      </p>

      <h2>Accessibility for beginners</h2>
      <p>
        The barrier to entry can feel high because projects often look for people
        with experience, but we all start without any. We promote those who are
        new to research, every project states whether it is beginner-friendly, and
        listers who support beginners earn recognition such as the Research Mentor
        badge. Everyone needed a first project once.
      </p>

      <h2>Who can supervise</h2>
      <p>
        Project supervisors must be one of: Consultants, Registrars, Dentists,
        Qualified Nurses, or staff grade at a hospital; or University Professors,
        Postdoctoral Researchers, or staff grade at a university. Verification is by
        institutional email (a UK university <code>.ac.uk</code> address or an NHS
        address).
      </p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Do not post misleading, fraudulent, or spam listings.</li>
        <li>
          Do not harass, discriminate against, or abuse other users.
        </li>
        <li>
          Do not misrepresent your identity, qualifications, or eligibility to
          supervise.
        </li>
        <li>
          Do not use the platform for anything unlawful or that breaches research
          ethics or patient confidentiality.
        </li>
      </ul>
      <p>
        We may remove content or suspend accounts that breach these principles.
        Questions? See our <a href="/about">About</a> page.
      </p>
    </Prose>
  );
}
