-- Guide pricing config (single row, admin-editable) and the PRIVATE storage
-- bucket for delivered guide files.
-- Apply with: node scripts/apply-sql.mjs drizzle/manual/0006_guides_seed.sql
-- Safe to re-run.

insert into guide_pricing_config (id, standard_price_pence, intro_price_pence, intro_quantity, blocked_countries)
values (1, 4500, 2500, 10, array['IN', 'PK'])
on conflict (id) do nothing;

-- No public policies: only the service role reads/writes. Files are served
-- through an authenticated app route tied to the buyer's account.
insert into storage.buckets (id, name, public)
values ('guide-files', 'guide-files', false)
on conflict (id) do update set public = false;
