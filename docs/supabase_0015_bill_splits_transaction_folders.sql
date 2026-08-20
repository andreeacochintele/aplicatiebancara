do $$
begin
    create type bill_split_status as enum ('OPEN', 'SETTLED', 'CANCELLED');
exception
    when duplicate_object then null;
end $$;

do $$
begin
    create type bill_split_participant_status as enum ('PENDING', 'PAID', 'DECLINED');
exception
    when duplicate_object then null;
end $$;

create table if not exists public.bill_splits (
    id uuid primary key,
    owner_user_id uuid not null references public.users(id),
    source_transaction_id uuid null references public.transactions(id),
    title varchar(255) not null,
    total_amount numeric(18, 2) not null,
    currency varchar(3) not null,
    status bill_split_status not null default 'OPEN',
    description varchar(500) null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_bill_splits_owner_user_id
    on public.bill_splits(owner_user_id);

create index if not exists ix_bill_splits_source_transaction_id
    on public.bill_splits(source_transaction_id);

create table if not exists public.bill_split_participants (
    id uuid primary key,
    bill_split_id uuid not null references public.bill_splits(id),
    participant_user_id uuid null references public.users(id),
    name varchar(255) not null,
    phone varchar(32) null,
    amount numeric(18, 2) not null,
    status bill_split_participant_status not null default 'PENDING',
    paid_transaction_id uuid null references public.transactions(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_bill_split_participants_split_id
    on public.bill_split_participants(bill_split_id);

create index if not exists ix_bill_split_participants_user_id
    on public.bill_split_participants(participant_user_id);

create table if not exists public.transaction_folders (
    id uuid primary key,
    owner_user_id uuid not null references public.users(id),
    name varchar(100) not null,
    color varchar(32) null,
    description varchar(500) null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_transaction_folders_owner_name unique (owner_user_id, name)
);

create index if not exists ix_transaction_folders_owner_user_id
    on public.transaction_folders(owner_user_id);

create table if not exists public.transaction_folder_items (
    id uuid primary key,
    folder_id uuid not null references public.transaction_folders(id),
    transaction_id uuid not null references public.transactions(id),
    added_at timestamptz not null default now(),
    constraint uq_transaction_folder_items_folder_transaction unique (folder_id, transaction_id)
);

create index if not exists ix_transaction_folder_items_folder_id
    on public.transaction_folder_items(folder_id);

create index if not exists ix_transaction_folder_items_transaction_id
    on public.transaction_folder_items(transaction_id);

notify pgrst, 'reload schema';
