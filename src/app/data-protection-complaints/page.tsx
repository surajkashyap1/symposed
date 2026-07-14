import type { Metadata } from "next";
import { Prose } from "@/components/prose";

// Generated from the Symposed Launch Legal and Policy Pack (July 2026).
// Regenerate rather than hand-editing large sections.

export const metadata: Metadata = {
  title: "Data Protection Complaints Procedure | Symposed",
  description: "How to raise a data protection complaint with Symposed.",
};

const html = "<h2 id=\"what-this-procedure-covers\">1. What this procedure covers</h2>\n<p>Use this procedure if you believe Symposed has collected, used,\nshared, retained, secured or otherwise handled personal information\nabout you in a way that breaches data protection law or our Privacy\nNotice.</p>\n<p>A request to access, erase, correct or exercise another data right\nmay also be handled under our data-rights process. We will identify the\ncorrect process even if you do not use legal terminology.</p>\n<h2 id=\"how-to-complain\">2. How to complain</h2>\n<p>Submit a complaint through our <a href=\"/contact\">contact form</a>.\nPlease provide:</p>\n<ul>\n<li><p>your name and the email address associated with your Symposed\naccount, if applicable;</p></li>\n<li><p>a clear description of what you believe happened;</p></li>\n<li><p>the relevant date, project, message, account or feature where\nknown;</p></li>\n<li><p>what outcome you are seeking; and</p></li>\n<li><p>any relevant evidence, while avoiding unnecessary patient or\nthird-party data.</p></li>\n</ul>\n<p>You do not need to quote the UK GDPR or any other legislation for us\nto treat a genuine concern as a data protection complaint.</p>\n<h2 id=\"what-we-will-do\">3. What we will do</h2>\n<p>1. Facilitate the complaint and record it through our complaints\nprocess.</p>\n<p>2. Acknowledge receipt within 30 days of receiving it.</p>\n<p>3. Without undue delay, take appropriate steps to respond, including\nmaking appropriate enquiries.</p>\n<p>4. Keep you informed where appropriate, particularly if the matter\nrequires more time or information.</p>\n<p>5. Without undue delay, tell you the outcome of the complaint and any\naction we have decided to take.</p>\n<p>We may ask for proportionate information to verify identity or\nclarify the concern. We will not ask for more information than\nreasonably necessary.</p>\n<h2 id=\"possible-outcomes\">4. Possible outcomes</h2>\n<p>Depending on the complaint, we may correct or delete information,\nchange a setting, explain our processing, improve a process, take\nsecurity or moderation action, refuse a request where a legal exception\napplies, or conclude that our processing was lawful. We will explain the\noutcome to the extent reasonably possible and lawful.</p>\n<h2 id=\"complaining-to-the-ico\">5. Complaining to the ICO</h2>\n<p>You can complain to the Information Commissioner's Office (ICO), the\nUK data protection regulator. We ask that you first give us an\nopportunity to address the matter, but you are not required to do so.\nInformation about making a complaint is available on the ICO\nwebsite.</p>\n<h2 id=\"contact\">6. Contact</h2>\n<p>Data protection complaints: our <a href=\"/contact\">contact\nform</a></p>\n<p>Controller: Symposed</p>\n";

export default function PolicyPage() {
  return (
    <Prose title="Data Protection Complaints Procedure" updated="6 July 2026">
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </Prose>
  );
}
