alter table public.cards
  add column if not exists pin_hash text;
