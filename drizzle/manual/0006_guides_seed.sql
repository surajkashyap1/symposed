-- Guide pricing config (single row, admin-editable) and the PRIVATE storage
-- bucket for delivered guide files.
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0006_guides_seed.sql
-- Safe to re-run.

-- Launch decision (2026-08-29): the first 50 guides are FREE — an intro price
-- of 0 makes checkout skip Stripe entirely, so payments can be wired up later
-- without blocking launch. Prices/quantity remain admin-editable on /admin/guides.
insert into guide_pricing_config (id, standard_price_pence, intro_price_pence, intro_quantity, blocked_countries)
values (1, 4500, 0, 50, array['IN', 'PK'])
on conflict (id) do nothing;

-- No public policies: only the service role reads/writes. Files are served
-- through an authenticated app route tied to the buyer's account.
insert into storage.buckets (id, name, public)
values ('guide-files', 'guide-files', false)
on conflict (id) do update set public = false;
