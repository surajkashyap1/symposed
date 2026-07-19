# Symposed

**The easiest way to get your first publication.**

A two-sided marketplace connecting UK university students and early-career
healthcare professionals with research opportunities — audits, systematic
reviews, posters, and studies. Students find approachable, clearly-scoped
projects (beginner-friendly work is surfaced first); supervisors list
opportunities and pick collaborators.

**Live at [symposed.org](https://symposed.org)** · Built and operated solo,
end to end: product design, UI, database, backend, deployment, and legal.

<!-- Add a screenshot: ![Symposed homepage](docs/screenshot.png) -->

## Features

- **Verified identities** — domain-based verification: `.ac.uk` emails verify
  students, NHS trust domains verify healthcare professionals. Verification
  gates who can supervise and post projects.
- **Rich profiles** — career stage, specialty, skills, publications,
  availability, with a computed profile-completeness score that nudges users
  toward a credible profile.
- **Project listings** — full-text search with filters (specialty, experience
  level, project type), separate *Beginner* and *Competitive* tabs, live
  application counts, and public Q&A on every listing.
- **Applications** — standardised forms with enforced word limits, applicant
  and lister dashboards (shortlist / accept / reject), and a fair-use rate
  limit of 3 applications per rolling 7 days.
- **Fair applicant ranking** — a transparent, server-side scoring model (no
  ML): every component is explainable to the lister, beginners are boosted,
  and prior experience is deliberately a minor factor.
- **Reviews & reputation** — reviews after a project completes, reliability
  scores, earned badges, and an anonymous review mode.
- **Trust & safety** — content reporting, an admin moderation queue, and a
  GDPR guard that blocks contact details and likely patient identifiers
  (including NHS-number detection via the mod-11 check digit) from ever being
  published.
- **Notifications & email** — in-app notifications plus transactional email
  (signup confirmation, password reset, application updates) via Resend.
- **Full legal footprint** — privacy policy, terms, acceptable use, cookie
  consent, research-integrity and safety policies, and a contact-form flow
  for complaints.

## Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 16 (App Router, React Server Components) + TypeScript |
| Database | Supabase Postgres (EU/London region) via Drizzle ORM |
| Auth | Supabase Auth (email/password, email confirmation, password reset) |
| Styling | Tailwind CSS 4 + shadcn/ui, custom "Scholarly Editorial" design system |
| Email | Resend |
| Testing | Playwright end-to-end suite |
| Hosting | Vercel, with scheduled maintenance via cron routes |

## Engineering notes

- **Defence in depth.** All database access happens in server code (server
  actions and route handlers); Row Level Security is enabled deny-all on
  every table as a backstop, so a leaked anon key exposes nothing.
- **Schema as source of truth.** A hand-written SQL schema
  (`docs/schema.sql`, ~20 tables) is mirrored in Drizzle
  (`src/db/schema.ts`) and applied through versioned migrations;
  cross-schema foreign keys into Supabase Auth live in manual migrations.
- **Rate limiting without infrastructure.** The application limit is computed
  from an indexed rolling time window in Postgres — no queue, no Redis, no
  extra table.
- **Tested like a product, not a demo.** The Playwright suite covers auth,
  profiles, listings, applications, reviews, notifications, admin, and public
  pages — plus a button-timing harness that catches perceived-latency
  regressions on interactive controls.
- **Designed, not templated.** A bespoke editorial design system (Fraunces +
  Hanken Grotesk, single claret accent) built for credibility with an
  anxious, non-expert audience; WCAG 2.1 AA contrast throughout, full
  keyboard navigation, light and dark first-class.
- **Error monitoring** persisted to the database with real 404s and hardened
  inputs and redirects — no third-party monitoring dependency.

## Running locally

```bash
npm install
cp .env.example .env.local   # Supabase + Resend credentials
npm run db:migrate            # apply Drizzle migrations
node scripts/apply-sql.mjs drizzle/manual/<file>.sql   # manual FKs + RLS
npm run dev
```

End-to-end tests: `e2e/run.sh` (Playwright).

## Project structure

```
docs/            product roadmap and canonical SQL schema
src/app/         routes (App Router): listings, applications, reviews,
                 admin, policies, auth flows
src/lib/         domain logic: ranking, verification, PII guard,
                 notifications, badges
src/db/          Drizzle schema and client
drizzle/         generated + manual migrations
e2e/             Playwright test suite
```
