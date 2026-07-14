import type { Metadata } from "next";
import { Prose } from "@/components/prose";

// Generated from the Symposed Launch Legal and Policy Pack (July 2026).
// Regenerate rather than hand-editing large sections.

export const metadata: Metadata = {
  title: "Security and Vulnerability Reporting | Symposed",
  description: "How to report a security concern to Symposed.",
};

const html = "<h2 id=\"reporting-a-security-concern\">1. Reporting a security\nconcern</h2>\n<p>If you believe you have found a security vulnerability affecting\nSymposed, report it privately via our <a href=\"/contact\">contact\nform</a>. Please include the affected URL or feature, a clear\ndescription, steps to reproduce where safe, and the potential\nimpact.</p>\n<p>If the issue involves exposed personal information, account\ncompromise or a patient-data disclosure, make that clear in the subject\nline so we can triage the incident appropriately.</p>\n<h2 id=\"rules-for-security-research\">2. Rules for security research</h2>\n<p>This policy does not provide blanket legal authorisation to test\nSymposed. You must not:</p>\n<ul>\n<li><p>access, download, alter or disclose another user's data beyond\nthe minimum accidental exposure necessary to identify and report a\nvulnerability;</p></li>\n<li><p>use social engineering, phishing, credential stuffing or stolen\ncredentials;</p></li>\n<li><p>deploy malware, carry out denial-of-service testing or materially\ndegrade the Service;</p></li>\n<li><p>perform destructive testing against production data;</p></li>\n<li><p>exfiltrate message content, contact information or\nresearch-related information;</p></li>\n<li><p>demand payment or threaten public disclosure as a condition of\nreporting; or</p></li>\n<li><p>publicly disclose an unresolved vulnerability before we have had\na reasonable opportunity to investigate and mitigate it.</p></li>\n</ul>\n<p>If you encounter user data accidentally, stop, do not retain or share\nit, tell us what was accessed and follow our instructions for secure\ndeletion where lawful.</p>\n<h2 id=\"our-response\">3. Our response</h2>\n<p>We will triage genuine reports and may contact you for further\ninformation. We do not currently promise a bug bounty or payment. We may\nrecognise good-faith reporters at our discretion where appropriate. We\nmay refer malicious activity to relevant providers or authorities.</p>\n<h2 id=\"account-security-reports\">4. Account-security reports</h2>\n<p>If you are a user and believe your account has been compromised,\ncontact our <a href=\"/contact\">contact form</a> and use any\npassword-reset or account-security tools available in the Service. Do\nnot send your password to Symposed.</p>\n";

export default function PolicyPage() {
  return (
    <Prose title="Security and Vulnerability Reporting" updated="6 July 2026">
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </Prose>
  );
}
