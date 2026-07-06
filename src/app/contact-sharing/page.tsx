import type { Metadata } from "next";
import { Prose } from "@/components/prose";

// Generated from the Symposed Launch Legal and Policy Pack (July 2026).
// Regenerate rather than hand-editing large sections.

export const metadata: Metadata = {
  title: "Contact Sharing and Off-platform Communications | Symposed",
  description: "How to share contact details safely on Symposed.",
};

const html = "<h2 id=\"public-contact-details\">1. Public contact details</h2>\n<p>Personal phone numbers and personal email addresses should not be\npublished in public project listings, public discussions or public\nprofile text. Where Symposed provides a specific professional contact\nfield in the future, the Service will explain its visibility before\npublication.</p>\n<h2 id=\"private-sharing-of-your-own-details\">2. Private sharing of your\nown details</h2>\n<p>You may voluntarily share your own email address, phone number or\nother contact details with another user in a private message or by using\na dedicated contact-sharing feature. Where a contact-sharing button is\nused, you should be able to choose which contact detail to disclose.</p>\n<p>Only share information you are comfortable giving to the recipient. A\nplatform warning is a reminder, not a guarantee about the recipient or\nhow the information will be used.</p>\n<h2 id=\"other-peoples-contact-details\">3. Other people's contact\ndetails</h2>\n<p>Do not share another person's private phone number, private email\naddress, home address or other personal information unless you have\ntheir permission or another lawful authority to do so. In particular, do\nnot circulate a supervisor's personal number merely because they are\nassociated with a project.</p>\n<h2 id=\"how-recipients-may-use-shared-details\">4. How recipients may use\nshared details</h2>\n<p>Contact details obtained through Symposed should be used only for the\ngenuine collaboration, professional contact or purpose for which they\nwere shared, unless another lawful basis and any required consent\napplies. Do not add users to marketing lists, sell details, scrape\ncontacts or distribute them to unrelated people.</p>\n<h2 id=\"moving-conversations-off-symposed\">5. Moving conversations off\nSymposed</h2>\n<p>Users are free to continue a genuine collaboration by email,\nWhatsApp, Teams or another appropriate service. Moving off-platform can\nreduce the amount of conversation content stored by Symposed, but it\ndoes not make unlawful or confidential sharing acceptable. Patient\ninformation and research data must still be handled using systems and\nprocesses approved by the responsible institution.</p>\n<p>Symposed cannot control, retrieve or delete copies of information\nthat a recipient has already copied to an external service or device. If\nanother user misuses contact details you shared through Symposed, report\nthe user and take any appropriate steps with the external service, your\ninstitution or relevant authority.</p>\n<h2 id=\"no-pressure-or-harassment\">6. No pressure or harassment</h2>\n<p>You do not have to share a phone number or personal email address to\nuse Symposed. Do not pressure another user to move off-platform or\nprovide contact details. Repeated unwanted contact, including contact\nafter rejection or blocking, may result in account action.</p>\n";

export default function PolicyPage() {
  return (
    <Prose title="Contact Sharing and Off-platform Communications" updated="6 July 2026">
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </Prose>
  );
}
