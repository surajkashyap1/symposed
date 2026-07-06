// Load-test seeding: ~1100 users, ~1250 projects, plus applications,
// questions, reviews, saved projects and notifications. All rows are tagged
// via loadtest.* emails so scripts/seed-load-cleanup.mjs can remove
// everything (auth.users delete cascades to profiles -> all child tables).
//
//   node scripts/seed-load.mjs
//
// Also creates two loginable accounts (via the GoTrue admin API):
//   loadtest.login.supervisor@example.com / Loadtest!123aA
//   loadtest.login.student@example.com    / Loadtest!123aA
import postgres from "postgres";
import { createClient } from "@supabase/supabase-js";
import { randomUUID } from "node:crypto";
import { config } from "dotenv";

config({ path: ".env.local" });

const sql = postgres(process.env.DATABASE_URL, { prepare: false, max: 4 });
const admin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY,
  { auth: { autoRefreshToken: false, persistSession: false } }
);

// Deterministic RNG so reruns produce comparable data.
let seed = 20260705;
function rnd() {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));
const chance = (p) => rnd() < p;
function daysAgo(n) {
  return new Date(Date.now() - n * 86400000 - int(0, 86399) * 1000);
}

const FIRST = ["Amelia","Oliver","Priya","James","Fatima","Tom","Aisha","Harry","Zainab","George","Chloe","Mohammed","Sophie","Arjun","Emily","Daniel","Grace","Yusuf","Hannah","Ben","Nadia","Sam","Leila","Jack","Mei","Ewan","Sara","Callum","Anya","Femi","Isla","Raj","Lucy","Omar","Freya","Kwame","Ella","Hassan","Rosie","Dev"];
const LAST = ["Patel","Smith","Khan","Jones","Williams","Ahmed","Brown","O'Connor","Taylor","Hussain","Davies","Evans","Wilson","Begum","Thomas","Roberts","Singh","Walker","Wright","Nguyen","Chen","Ali","Murphy","Campbell","Kelly","Shah","Osei","MacLeod","Kaur","Adeyemi"];
const SPECIALTIES = ["Cardiology","Respiratory","Gastroenterology","Neurology","Oncology","Paediatrics","Psychiatry","Emergency Medicine","General Surgery","Orthopaedics","Obstetrics & Gynaecology","Anaesthetics","Radiology","Dermatology","Ophthalmology","ENT","Urology","Geriatrics","Public Health","General Practice"];
const UNIS = ["University of Oxford","University of Cambridge","Imperial College London","King's College London","University College London","University of Edinburgh","University of Manchester","University of Birmingham","University of Bristol","Cardiff University","University of Leeds","Newcastle University","University of Glasgow","Queen's University Belfast","University of Sheffield","University of Nottingham"];
const STAGES_STUDENT = ["medical_student","dental_student","nursing_student","masters_student","phd_student","other_student"];
const STAGES_SENIOR = ["foundation_doctor","junior_doctor","registrar","consultant","dentist","qualified_nurse","physician_associate","physiotherapist","pharmacist","professor","postdoc"];
const TYPES = ["audit","systematic_review","literature_review","case_study","retrospective","prospective_study","poster","teaching","other"];
const EXP = ["beginner_welcome","some_experience","experienced_only"];
const ROLES = ["Data extraction","Literature screening","Referencing","Audit admin","Formatting","Poster creation","Presentation slides","Writing","Statistics"];

const TITLE_TEMPLATES = [
  (s) => `Audit of ${s} referral pathways at a district general hospital`,
  (s) => `Systematic review: outcomes in ${s.toLowerCase()} interventions 2015-2025`,
  (s) => `Retrospective cohort study of ${s.toLowerCase()} admissions during winter pressures`,
  (s) => `Case series: atypical presentations in ${s}`,
  (s) => `Poster for regional ${s.toLowerCase()} conference — co-authors needed`,
  (s) => `Literature review on AI-assisted diagnostics in ${s}`,
  (s) => `Quality improvement project: reducing waiting times in ${s} clinics`,
  (s) => `${s} teaching series for foundation doctors — content contributors wanted`,
  (s) => `Prospective service evaluation of virtual ${s.toLowerCase()} clinics`,
  (s) => `Closing the loop: re-audit of ${s.toLowerCase()} documentation standards`,
];

const DESC_PARAS = [
  "We are looking for motivated students to join an established project team. This is a genuine opportunity for a first publication with fair authorship for meaningful contribution.",
  "The data collection tools are already approved and registered with the local audit department. Your role will involve extracting anonymised data, helping with analysis, and contributing to the write-up.",
  "No prior research experience is required — full training will be given, including how to use the data extraction sheet and reference manager. Weekly 30-minute check-ins over Teams.",
  "We aim to submit to a peer-reviewed journal within four months, with an interim abstract submitted to a national conference. All contributors meeting ICMJE criteria will be named authors.",
  "Ideal for anyone building a portfolio for specialty applications. Evidence of audit participation and presentation counts towards several application scoring frameworks.",
  "You should be able to commit a few hours per week. Reliability matters more than experience: we would rather have consistent contributors than impressive CVs.",
];

// Edge cases we deliberately include to shake out UI bugs.
const EDGE_TITLES = [
  "A very long project title designed to test how the interface behaves when a supervisor writes an entire abstract into the title field, including methodology, setting, and a subtitle about outcomes in a multicentre retrospective cohort across fourteen NHS trusts in England and Wales",
  "Café-au-lait macules & neurofibromatosis — naïve Bayes über-analysis (émigré cohort) 🧬",
  "<script>alert('xss')</script> Injection-looking title audit",
  "ALLCAPSTITLEWITHNOSPACESTOTESTOVERFLOWBEHAVIOURINCARDSANDDETAILPAGESXXXXXXXXXXXXXXXXXXXXXXXX",
];

const N_SUPERVISORS = 220;
const N_STUDENTS = 900;
const N_PROJECTS = 1250;
const PASSWORD_HASH = "$2a$10$loadtestloadtestloadteuMLoJmEqZG8dGVLDJPtPHFyvHW7z2Ki"; // not loginable
const now = new Date();

async function insertAuthUsers(rows) {
  // Direct insert into auth.users: fast and cascade-cleanable. Token/text
  // columns must be '' (not null) or GoTrue chokes when scanning rows.
  for (let i = 0; i < rows.length; i += 200) {
    const chunk = rows.slice(i, i + 200).map((u) => ({
      instance_id: "00000000-0000-0000-0000-000000000000",
      id: u.id,
      aud: "authenticated",
      role: "authenticated",
      email: u.email,
      encrypted_password: PASSWORD_HASH,
      email_confirmed_at: u.createdAt,
      raw_app_meta_data: { provider: "email", providers: ["email"] },
      raw_user_meta_data: { full_name: u.fullName },
      created_at: u.createdAt,
      updated_at: u.createdAt,
      confirmation_token: "",
      recovery_token: "",
      email_change_token_new: "",
      email_change: "",
      email_change_token_current: "",
      phone_change: "",
      phone_change_token: "",
      reauthentication_token: "",
    }));
    await sql`insert into auth.users ${sql(chunk)}`;
  }
}

async function main() {
  const t0 = Date.now();
  const existing = await sql`select count(*)::int n from auth.users where email like 'loadtest.%'`;
  if (existing[0].n > 0) {
    console.error(`Found ${existing[0].n} existing loadtest users — run seed-load-cleanup.mjs first.`);
    process.exit(1);
  }

  // ---- users -----------------------------------------------------------
  const users = [];
  for (let i = 0; i < N_SUPERVISORS + N_STUDENTS; i++) {
    const isSup = i < N_SUPERVISORS;
    const fullName = `${pick(FIRST)} ${pick(LAST)}`;
    users.push({
      id: randomUUID(),
      email: `loadtest.${isSup ? "sup" : "stu"}.${i}@example.com`,
      fullName,
      isSup,
      careerStage: isSup ? pick(STAGES_SENIOR) : pick(STAGES_STUDENT),
      university: pick(UNIS),
      specialty: chance(0.8) ? pick(SPECIALTIES) : null,
      isVerified: isSup ? true : chance(0.7),
      createdAt: daysAgo(int(1, 180)),
    });
  }
  await insertAuthUsers(users);
  console.log(`auth.users: ${users.length} inserted (${Date.now() - t0}ms)`);

  for (let i = 0; i < users.length; i += 200) {
    const chunk = users.slice(i, i + 200).map((u) => ({
      id: u.id,
      email: u.email,
      full_name: u.fullName,
      career_stage: u.careerStage,
      university: u.university,
      specialty: u.specialty,
      summary: chance(0.6)
        ? `${u.isSup ? "Clinician" : "Student"} at ${u.university} with an interest in ${(u.specialty ?? "clinical research").toLowerCase()}. ${pick(DESC_PARAS)}`
        : null,
      is_verified: u.isVerified,
      can_supervise: u.isSup,
      is_new_researcher: !u.isSup && chance(0.8),
      availability_hours_per_week: chance(0.5) ? int(1, 15) : null,
      profile_completeness: int(20, 100),
      created_at: u.createdAt,
      updated_at: u.createdAt,
    }));
    await sql`insert into public.profiles ${sql(chunk)}`;
  }
  const supervisors = users.filter((u) => u.isSup);
  const students = users.filter((u) => !u.isSup);
  console.log(`profiles: ${users.length} inserted`);

  // ---- loginable accounts ---------------------------------------------
  const login = {};
  for (const [key, canSup] of [["supervisor", true], ["student", false]]) {
    const email = `loadtest.login.${key}@example.com`;
    const { data, error } = await admin.auth.admin.createUser({
      email,
      password: "Loadtest!123aA",
      email_confirm: true,
      user_metadata: { full_name: `Loadtest ${key[0].toUpperCase()}${key.slice(1)}` },
    });
    if (error) throw new Error(`createUser ${email}: ${error.message}`);
    await sql`
      insert into public.profiles (id, email, full_name, career_stage, university, is_verified, can_supervise)
      values (${data.user.id}, ${email}, ${"Loadtest " + key}, ${canSup ? "consultant" : "medical_student"},
              'University of Oxford', true, ${canSup})
      on conflict (id) do update set is_verified = true, can_supervise = ${canSup}
    `;
    login[key] = data.user.id;
    console.log(`loginable: ${email} / Loadtest!123aA`);
  }

  // ---- projects ---------------------------------------------------------
  const projects = [];
  for (let i = 0; i < N_PROJECTS; i++) {
    const owner = i < 12 ? { id: login.supervisor } : pick(supervisors);
    const specialty = pick(SPECIALTIES);
    const r = rnd();
    const status = r < 0.75 ? "open" : r < 0.85 ? "in_progress" : r < 0.93 ? "completed" : r < 0.98 ? "closed" : "draft";
    const createdAt = daysAgo(int(0, 150));
    const nParas = int(1, 6);
    let description = Array.from({ length: nParas }, () => pick(DESC_PARAS)).join("\n\n");
    let title = pick(TITLE_TEMPLATES)(specialty);
    if (i < EDGE_TITLES.length) title = EDGE_TITLES[i];
    if (i === EDGE_TITLES.length) description = DESC_PARAS.join("\n\n").repeat(8); // very long body
    projects.push({
      id: randomUUID(),
      owner_id: owner.id,
      title,
      description,
      project_type: pick(TYPES),
      experience_level: pick(EXP),
      specialty: chance(0.9) ? specialty : null,
      role_category: chance(0.6) ? pick(ROLES) : null,
      is_beginner_friendly: chance(0.55),
      positions_available: int(1, 4),
      status,
      application_deadline: chance(0.6)
        ? new Date(Date.now() + int(-20, 90) * 86400000).toISOString().slice(0, 10)
        : null,
      created_at: createdAt,
      updated_at: createdAt,
    });
  }
  for (let i = 0; i < projects.length; i += 100) {
    await sql`insert into public.projects ${sql(projects.slice(i, i + 100))}`;
  }
  console.log(`projects: ${projects.length} inserted`);

  // ---- applications ------------------------------------------------------
  const apps = [];
  const nonDraft = projects.filter((p) => p.status !== "draft");
  for (const p of nonDraft) {
    // most projects get 0-8 applicants; the login supervisor's first project gets 45
    const n = p.owner_id === login.supervisor && apps.length < 45 ? 45 : int(0, 8);
    const shuffled = [...students].sort(() => rnd() - 0.5).slice(0, n);
    for (const s of shuffled) {
      apps.push({
        project_id: p.id,
        applicant_id: s.id,
        status: pick(["pending","pending","pending","shortlisted","accepted","rejected","withdrawn"]),
        motivation: `I am keen to contribute to this project because ${pick(DESC_PARAS).toLowerCase()}`,
        suitability: `I have completed relevant modules and can commit ${int(2, 10)} hours a week. ${pick(DESC_PARAS)}`,
        hours_per_week: chance(0.7) ? int(1, 12) : null,
        skills_summary: chance(0.6) ? pick(ROLES) : null,
        created_at: daysAgo(int(0, 60)),
      });
    }
  }
  // login student applies to a few open projects
  const openProjects = projects.filter((p) => p.status === "open");
  for (const p of openProjects.slice(0, 5)) {
    apps.push({
      project_id: p.id,
      applicant_id: login.student,
      status: pick(["pending","shortlisted","accepted"]),
      motivation: "Keen to get my first publication; I can start immediately.",
      suitability: "Completed audit training and have used Excel and Zotero.",
      hours_per_week: 5,
      skills_summary: "Data extraction",
      created_at: daysAgo(int(0, 10)),
    });
  }
  for (let i = 0; i < apps.length; i += 200) {
    await sql`insert into public.applications ${sql(apps.slice(i, i + 200))}`;
  }
  console.log(`applications: ${apps.length} inserted`);

  // ---- listing questions -------------------------------------------------
  const questions = [];
  for (const p of openProjects) {
    const n = int(0, 3);
    for (let i = 0; i < n; i++) {
      const answered = chance(0.6);
      const createdAt = daysAgo(int(0, 40));
      questions.push({
        project_id: p.id,
        asker_id: pick(students).id,
        question: pick([
          "Is this suitable for a second-year student with no prior research experience?",
          "Will contributors meeting ICMJE criteria be named authors on the final paper?",
          "Is the data collection remote, or does it require on-site access?",
          "What is the expected timeline to submission?",
          "Do you need ethics approval for this, or is it registered as an audit?",
        ]),
        answer: answered ? pick(DESC_PARAS) : null,
        answered_at: answered ? new Date(createdAt.getTime() + 86400000) : null,
        created_at: createdAt,
      });
    }
  }
  for (let i = 0; i < questions.length; i += 200) {
    await sql`insert into public.listing_questions ${sql(questions.slice(i, i + 200))}`;
  }
  console.log(`listing_questions: ${questions.length} inserted`);

  // ---- reviews on completed projects --------------------------------------
  const reviews = [];
  for (const p of projects.filter((x) => x.status === "completed")) {
    const members = [...students].sort(() => rnd() - 0.5).slice(0, int(1, 3));
    for (const m of members) {
      // postgres.js bulk insert requires identical keys on every row, so
      // both directions carry the full column set (nulls where n/a).
      reviews.push({
        project_id: p.id, reviewer_id: p.owner_id, reviewee_id: m.id,
        direction: "supervisor_to_member",
        rating_overall: (int(6, 10) / 2).toFixed(1),
        reliability: int(3, 5), communication: int(3, 5), contribution: int(2, 5),
        meets_deadlines: int(3, 5),
        supervision: null, teaching: null, fair_authorship: null,
        comment: chance(0.7) ? "Reliable contributor, would work with again." : null,
        is_anonymous: false, created_at: daysAgo(int(0, 30)),
      });
      reviews.push({
        project_id: p.id, reviewer_id: m.id, reviewee_id: p.owner_id,
        direction: "member_to_supervisor",
        rating_overall: (int(6, 10) / 2).toFixed(1),
        reliability: null, communication: null, contribution: null,
        meets_deadlines: null,
        supervision: int(3, 5), teaching: int(2, 5), fair_authorship: int(3, 5),
        comment: chance(0.7) ? "Clear expectations and fair authorship. Recommended." : null,
        is_anonymous: chance(0.3), created_at: daysAgo(int(0, 30)),
      });
    }
  }
  for (let i = 0; i < reviews.length; i += 200) {
    await sql`insert into public.reviews ${sql(reviews.slice(i, i + 200))}`;
  }
  console.log(`reviews: ${reviews.length} inserted`);

  // ---- saved projects + notifications for login users ---------------------
  const saved = openProjects.slice(0, 12).map((p) => ({
    profile_id: login.student, project_id: p.id, created_at: daysAgo(int(0, 5)),
  }));
  await sql`insert into public.saved_projects ${sql(saved)}`;

  const notifs = [];
  for (let i = 0; i < 60; i++) {
    const target = i % 2 ? login.student : login.supervisor;
    notifs.push({
      profile_id: target,
      type: pick(["application","review","system","match"]),
      title: pick([
        "New application received",
        "Your application was shortlisted",
        "You have a new review",
        "New projects match your interests",
      ]),
      body: "Load-test notification body.",
      link: "/projects",
      read_at: chance(0.5) ? daysAgo(int(0, 3)) : null,
      created_at: daysAgo(int(0, 20)),
    });
  }
  await sql`insert into public.notifications ${sql(notifs)}`;
  console.log(`saved_projects: ${saved.length}, notifications: ${notifs.length}`);

  console.log(`Done in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  await sql.end();
}

main().catch(async (e) => {
  console.error(e);
  await sql.end();
  process.exit(1);
});
