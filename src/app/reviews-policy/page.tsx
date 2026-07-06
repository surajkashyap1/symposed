import type { Metadata } from "next";
import { Prose } from "@/components/prose";

// Generated from the Symposed Launch Legal and Policy Pack (July 2026).
// Regenerate rather than hand-editing large sections.

export const metadata: Metadata = {
  title: "Reviews, Reputation, Badges and Verification | Symposed",
  description: "How reviews, badges and verification work on Symposed.",
};

const html = "<h2 id=\"purpose\">1. Purpose</h2>\n<p>Symposed uses project-based reviews and platform indicators to help\nusers assess reliability and to recognise genuine participation,\nmentoring and beginner support. These features are intended as trust\nsignals, not professional accreditation.</p>\n<h2 id=\"reviews\">2. Reviews</h2>\n<ul>\n<li><p>A review must relate to a genuine project interaction or\ncollaboration that the reviewer directly experienced.</p></li>\n<li><p>Reviews must be honest, relevant, proportionate and submitted in\ngood faith.</p></li>\n<li><p>Do not include patient data, confidential project information,\nprivate contact details or unnecessary personal information.</p></li>\n<li><p>Do not buy, sell, trade or coerce reviews. Do not make a positive\nreview a condition of authorship or threaten a negative review to obtain\nwork.</p></li>\n<li><p>Do not use a review to harass, discriminate against, doxx or\nretaliate against another user.</p></li>\n<li><p>We may ask for information showing that a genuine project\nconnection existed and may remove reviews that breach policy or cannot\nreasonably be linked to platform activity.</p></li>\n</ul>\n<h2 id=\"reliability-indicators\">3. Reliability indicators</h2>\n<p>Symposed may display reliability indicators based on project-related\nreviews, completion information, response or platform activity, or other\npublished criteria. A reliability indicator is a platform-generated\nsignal and may be incomplete, disputed or affected by limited data. It\nis not a guarantee that a person will perform in a particular way.</p>\n<p>Criteria may change as the platform develops. Where a material\nfactual error is identified, users can request review through the appeal\nor support route.</p>\n<h2 id=\"beginner-and-mentor-recognition\">4. Beginner and mentor\nrecognition</h2>\n<p>A New Researcher or similar indicator may identify a user with\nlimited recorded project experience on Symposed. It does not mean the\nperson lacks research experience elsewhere. A Research Mentor or similar\nbadge may recognise platform-defined beginner support. It does not\ncertify teaching competence or professional standing.</p>\n<p>Symposed may give beginner-friendly projects or recognised mentors\nadditional platform visibility or non-cash benefits. Criteria and\nincentives may change and may be removed where misused.</p>\n<h2 id=\"verification\">5. Verification</h2>\n<p>Verification may use an institutional email address or other\nevidence. Verification confirms only the specific verification step\ncompleted at the time. It is not a background check and does not\nguarantee identity, current employment, professional registration, good\nstanding, authority to supervise, or project legitimacy.</p>\n<p>Users should carry out their own appropriate checks. We may revoke\nverification where information is inaccurate, outdated, misused or no\nlonger meets the criteria.</p>\n<h2 id=\"challenges-and-appeals\">6. Challenges and appeals</h2>\n<p>If you believe a review, badge, verification status or reliability\nindicator breaches this policy or contains a material factual error, use\nthe report or appeal route. Disagreement alone does not guarantee\nremoval. We may restrict a review while investigating and may seek\ninformation from the users involved.</p>\n";

export default function PolicyPage() {
  return (
    <Prose title="Reviews, Reputation, Badges and Verification" updated="6 July 2026">
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </Prose>
  );
}
