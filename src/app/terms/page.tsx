import type { Metadata } from "next";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "Terms of Use | Symposed",
  description: "The terms governing your use of Symposed.",
};

export default function TermsPage() {
  return (
    <Prose title="Terms of Use" updated="June 2026">
      <p>
        These terms govern your use of Symposed. By creating an account or using the
        platform, you agree to them and to our{" "}
        <a href="/ethos">Ethos &amp; usage policy</a>.{" "}
        <strong>This is a template and must be reviewed by a qualified
        professional before launch.</strong>
      </p>

      <h2>Eligibility &amp; accounts</h2>
      <p>
        You must provide accurate information and keep your account secure. To post
        opportunities as a supervisor, you must meet the eligibility criteria and
        verify an institutional email. You are responsible for activity on your
        account.
      </p>

      <h2>Conduct</h2>
      <p>
        You agree to use the platform in good faith, to apply only to opportunities
        you intend to pursue, and not to post misleading, unlawful, or harmful
        content. Application limits and other fair-use measures apply as described
        in our ethos.
      </p>

      <h2>Content &amp; reviews</h2>
      <p>
        You retain ownership of content you post but grant us a licence to display
        it on the platform. Reviews must be honest and based on genuine project
        experience. We may remove content that breaches these terms.
      </p>

      <h2>No guarantee of outcomes</h2>
      <p>
        Symposed is a marketplace that connects people. We do not guarantee that you
        will find a project, a collaborator, a supervisor, or a publication, and we
        are not a party to any agreement you make with other users. Authorship,
        supervision, and project arrangements are between you and your
        collaborators, and remain subject to relevant research-ethics and
        institutional rules.
      </p>

      <h2>Liability</h2>
      <p>
        The service is provided &ldquo;as is&rdquo;. To the extent permitted by law,
        we are not liable for indirect or consequential loss arising from use of the
        platform. Nothing in these terms limits liability that cannot be limited by
        law.
      </p>

      <h2>Changes &amp; termination</h2>
      <p>
        We may update these terms and will indicate the date of changes. You may
        close your account at any time; we may suspend accounts that breach these
        terms.
      </p>
    </Prose>
  );
}
