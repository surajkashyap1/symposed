import type { Metadata } from "next";
import Link from "next/link";
import { Prose } from "@/components/prose";

export const metadata: Metadata = {
  title: "About Symposed",
  description:
    "Why Symposed exists: making healthcare research more accessible, organised and collaborative.",
};

export default function AboutPage() {
  return (
    <Prose title="Why Symposed exists">
      <p>
        Research can shape careers, open doors and introduce you to areas of
        healthcare you may never otherwise experience. Yet finding the
        opportunity to get involved is often unnecessarily difficult.
      </p>

      <p>
        For many students and early-career healthcare professionals, the usual
        route into research, audits and presentations is still cold-emailing
        potential supervisors, asking friends, joining WhatsApp groups,
        contacting societies or simply hoping to know the right person.
        Opportunities are scattered across informal networks, and people who
        are keen to contribute often have no simple way of finding them.
      </p>

      <p>
        We created{" "}
        <em>Symposed because we believe there should be a better way.</em>
      </p>

      <p>
        Symposed is a platform for sharing research opportunities and bringing
        together people who want to work on them. A supervisor may already
        have an established project and need enthusiastic collaborators. A
        student may have found a supervisor but need a team to share the
        workload. Others may simply have a research idea and want to meet
        people with similar interests before approaching an appropriate
        supervisor.
      </p>

      <p>
        The aim is simple:{" "}
        <em>
          make it easier for the right people to find each other and turn
          interest into real projects.
        </em>
      </p>

      <p>
        Finding an opportunity is only part of the problem. Research projects
        often stall because timelines become unclear, workloads are difficult
        to manage, expectations differ or team members can no longer
        contribute. Valuable ideas can be abandoned even when other motivated
        people would be willing to help.
      </p>

      <p>
        Symposed aims to give those projects another route forward by making
        opportunities, collaborations and available roles easier to share.
      </p>

      <p>
        Whether you are looking for your first project, your next
        collaborator, or a team to help move an existing idea forward,
        Symposed is built to make healthcare research more accessible,
        organised and collaborative.
      </p>

      <p>
        <em>
          Go beyond cold emails. Find opportunities. Build teams. Move
          research forward.
        </em>
      </p>

      <p>
        <Link href="/projects">Browse open projects</Link> or{" "}
        <Link href="/signup">create a free account</Link> to get started.
      </p>
    </Prose>
  );
}
