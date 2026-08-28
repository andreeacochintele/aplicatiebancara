-- Mirrors migration 0036_card_pin_hash / 0043_repair_card_pin_hash.
-- Run this in Supabase SQL Editor when DATABASE_BACKEND=supabase_rest is used.
-- Idempotent: safe to re-run.

begin;

alter table public.cards
  add column if not exists pin_hash varchar(255);

notify pgrst, 'reload schema';

commit;
