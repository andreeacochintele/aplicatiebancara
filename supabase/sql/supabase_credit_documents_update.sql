-- Credit score and loan application document storage for Supabase REST mode.
-- Run this in the Supabase SQL editor before testing document upload/review flows.

do $$
begin
  if not exists (select 1 from pg_type where typname = 'credit_document_purpose') then
    create type credit_document_purpose as enum ('CREDIT_SCORE', 'LOAN_APPLICATION');
  end if;

  if not exists (select 1 from pg_type where typname = 'credit_document_status') then
    create type credit_document_status as enum ('UPLOADED', 'APPROVED', 'REJECTED', 'NEEDS_MORE_INFO');
  end if;
end $$;

create table if not exists credit_documents (
  id uuid primary key,
  user_id uuid not null references users(id),
  application_id uuid null references credit_applications(id),
  purpose credit_document_purpose not null,
  document_type varchar(80) not null,
  file_name varchar(255) not null,
  content_type varchar(100),
  file_size integer not null default 0,
  content_base64 text,
  status credit_document_status not null default 'UPLOADED',
  evaluation_score integer,
  review_note varchar(500),
  uploaded_at timestamptz not null,
  reviewed_at timestamptz,
  reviewed_by_admin_id uuid null references users(id)
);

alter table credit_documents
  add column if not exists application_id uuid null references credit_applications(id),
  add column if not exists content_base64 text,
  add column if not exists evaluation_score integer,
  add column if not exists review_note varchar(500),
  add column if not exists reviewed_at timestamptz,
  add column if not exists reviewed_by_admin_id uuid null references users(id);

create index if not exists ix_credit_documents_user_id on credit_documents(user_id);
create index if not exists ix_credit_documents_application_id on credit_documents(application_id);
create index if not exists ix_credit_documents_status on credit_documents(status);
create index if not exists ix_credit_documents_purpose on credit_documents(purpose);
