import type { Metadata } from "next";
import Link from "next/link";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "Policies | Symposed",
  description: "All Symposed policies, guidelines and procedures in one place.",
};

const POLICIES = [
  { href: "/privacy", label: "Privacy Notice", blurb: "How we collect, use and protect personal information." },
  { href: "/terms", label: "Terms of Service", blurb: "The terms governing your use of Symposed." },
  { href: "/cookies", label: "Cookie Policy", blurb: "The cookies and similar technologies we use." },
  { href: "/acceptable-use", label: "Acceptable Use Policy", blurb: "What you may and may not do on Symposed." },
  { href: "/community-guidelines", label: "Community Guidelines", blurb: "How we expect members to treat each other." },
  { href: "/posting-guidelines", label: "Project Posting and Application Guidelines", blurb: "What makes a good, compliant listing and application." },
  { href: "/research-integrity", label: "Research Integrity, Authorship and Collaboration", blurb: "Integrity, ethics and authorship expectations." },
  { href: "/contact-sharing", label: "Contact Sharing Policy", blurb: "How to share contact details safely." },
  { href: "/reviews-policy", label: "Reviews, Reputation, Badges and Verification", blurb: "How reviews, badges and verification work." },
  { href: "/safety", label: "Safety, Content Reporting, Moderation and Appeals", blurb: "How to report content and how moderation works." },
  { href: "/data-protection-complaints", label: "Data Protection Complaints Procedure", blurb: "How to raise a data protection complaint." },
  { href: "/legal-complaints", label: "Legal Content Complaints and Notice-and-Takedown", blurb: "How to send us a legal complaint about content." },
  { href: "/security-policy", label: "Security and Vulnerability Reporting", blurb: "How to report a security concern." },
  { href: "/ethos", label: "Ethos and Usage Policy", blurb: "The principles that keep Symposed fair and welcoming." },
];

export default function PoliciesPage() {
  return (
    <Prose
      title="Policies"
      intro="Everything that governs how Symposed works, in one place."
    >
      <ul>
        {POLICIES.map((p) => (
          <li key={p.href}>
            <Link href={p.href}>{p.label}</Link>{" "}
            <span className="text-muted-foreground">, {p.blurb}</span>
          </li>
        ))}
      </ul>
    </Prose>
  );
}
