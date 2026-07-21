# Environments & the test → production workflow

Two environments, isolated by **database** so test data never touches real
users:

| Environment | Vercel deploy | Database (Supabase project) |
| --- | --- | --- |
| **Production** | `main` branch → `symposed.org` | `symposed` (prod) |
| **Preview / staging** | any other branch + PRs → `*.vercel.app` preview URL | `symposed-staging` |

Vercel already builds a **Preview Deployment** for every branch and PR
automatically. The only thing that makes it a *safe* test server is pointing its
env vars at a separate database — that's what the one-time setup below does.

---

## The day-to-day workflow

Never push straight to `main` again. Instead:

```bash
git checkout -b my-change        # branch off main
# ...make changes...
git push -u origin my-change     # Vercel builds a Preview at a unique URL
```

- Open the preview URL Vercel comments on the push / PR. It runs your branch's
  code against the **staging** database — sign up, apply, accept, etc. freely.
- When it looks right, open a PR and merge to `main`. Merging deploys to
  **production**.

Rule of thumb: **branch → preview (staging DB) → merge to main → production.**

---

## One-time setup

### 1. Create the staging Supabase project (your side)

1. Supabase dashboard → **New project** → name `symposed-staging`, **region
   `eu-west-2` (London)** to match prod, set a DB password.
2. Grab, from **Project Settings → Database → Connection string**:
   - **Session pooler** URL (port **5432**) — for migrations.
   - **Transaction pooler** URL (port **6543**) — for the app at runtime.
3. From **Project Settings → API**: the Project URL, the `anon` key, and the
   `service_role` key.

### 2. Provision the staging schema (one command)

Point the bootstrap at the staging **session pooler** URL. It applies every
drizzle migration plus the manual cross-schema SQL (auth FK, realtime, storage,
RLS), so staging matches prod exactly:

```bash
MIGRATION_DATABASE_URL="postgresql://…@…pooler.supabase.com:5432/postgres" \
  npm run db:bootstrap
```

It prints the target host first so you can confirm it's staging, not prod.

### 3. Point Vercel Previews at staging (your side)

In Vercel → Project → **Settings → Environment Variables**, add each of these
scoped to **Preview only** (leave Production pointing at the prod project):

| Variable | Value (staging) |
| --- | --- |
| `DATABASE_URL` | staging **transaction** pooler URL (`:6543`) |
| `MIGRATION_DATABASE_URL` | staging **session** pooler URL (`:5432`) |
| `NEXT_PUBLIC_SUPABASE_URL` | staging Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | staging anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | staging service_role key |
| `NEXT_PUBLIC_SITE_URL` | leave unset (Vercel injects the preview URL) |

Email (`RESEND_*`) can stay unset on Preview so tests never send real mail — or
set it to the same key with a test sender if you want to exercise the flow.

Redeploy any open preview after changing env vars.

---

## Applying future migrations

- **Prod:** `npm run db:migrate` runs against the DB in `.env.local` (prod).
- **Staging:** prefix with the staging session URL:
  ```bash
  MIGRATION_DATABASE_URL="postgresql://…:5432/postgres" npm run db:migrate
  ```

Run new migrations on **staging first** (via the preview), then on prod when you
merge. New manual SQL in `drizzle/manual/` must be added to `scripts/bootstrap-db.mjs`
so fresh databases keep working.
