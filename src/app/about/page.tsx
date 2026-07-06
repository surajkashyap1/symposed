import type { Metadata } from "next";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "About Symposed",
  description:
    "Why Symposed exists: making research opportunities accessible to all UK students and healthcare workers, not only the well-connected.",
};

export default function AboutPage() {
  return (
    <Prose
      title="About Symposed"
      intro="Bringing research opportunities closer to students and healthcare professionals."
    >
      <p>
        Publications, audits and poster presentations are nowadays essential when
        applying for postgraduate training in medicine, dentistry, nursing and
        allied healthcare disciplines. Competition is rapidly increasing with the
        availability of AI tools, and portfolio requirements change every year.
        However, finding opportunities for research, audits and posters is often
        difficult. Common strategies include cold-emailing potential supervisors,
        WhatsApp groups, asking friends, societies, word of mouth, and having good
        connections.
      </p>
      <p>
        Supervisors can easily find people to work on their projects within their
        own circles, but some still give opportunities to those who are passionate
        about their work and, most importantly, to those who ask. Given that
        students need these opportunities more than supervisors need students, the
        rudimentary approaches mentioned previously remain the main way of finding
        and starting research projects. We felt this process is very disorganised,
        and that a platform dedicated to sharing these projects would help
        streamline things.
      </p>
      <p>
        The aim of this platform is to have a space where anyone, whether student
        or supervisor, can post research opportunities. The opportunity may already
        have an established supervisor with a project idea. Alternatively, neither
        may be established, and the lister simply needs collaborators with similar
        goals so they can plan projects together and contact appropriate
        supervisors.
      </p>
      <p>
        Another key issue we hope to address is that most research opportunities do
        not usually translate to a publication or presentation. Even when projects
        are started, timelines tend to drag on, expectations from students and
        supervisors are unclear, motivation is lost, and projects fall apart. For
        situations like these, there will be other students interested in the
        project who can pick up where it was left off, and such opportunities will
        also be posted.
      </p>

      <h2>Our mission</h2>
      <ul>
        <li>
          Make research opportunities accessible to all UK students and healthcare
          workers, not only the well-connected or already experienced.
        </li>
        <li>
          Create a trusted marketplace for projects, collaborators, and
          supervisors.
        </li>
        <li>
          Promote those who are new to research, and clarify whether projects are
          suitable for beginners, to improve accessibility.
        </li>
      </ul>

      <p>
        Read more about how we keep the platform fair and trustworthy in our{" "}
        <a href="/ethos">ethos &amp; usage policy</a>.
      </p>
    </Prose>
  );
}
