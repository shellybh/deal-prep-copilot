-- Phase 2C (API): knowledge base management (ARCHITECTURE §4.1, §6.0.2; D4, D13, D14, D35)
-- 1. Generic DB-backed job queue (D14), used now for ingestion and in Phase 4 for research runs.
-- 2. Soft delete for documents, so future briefing sources can still name a deleted document.
-- 3. Atomic version swap for "replace": the old version stays searchable until the new one is indexed.
-- 4. Private Storage bucket kb-documents (20 MB, allowed types, D35). Backend only (service key).

-- ---------------------------------------------------------------- jobs
create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('ingest_document')),   -- Phase 4 adds 'research_run'
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  attempts int not null default 0 check (attempts >= 0),
  max_attempts int not null default 3 check (max_attempts >= 1),
  run_after timestamptz not null default now(),     -- retry backoff: not claimed before this time
  locked_by text,                                    -- worker id
  heartbeat_at timestamptz,                          -- stale running jobs are recovered on startup
  started_at timestamptz,
  finished_at timestamptz,
  error text,
  created_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Claim order: oldest queued job of a kind that is due.
create index jobs_queued_idx on public.jobs (kind, created_at) where status = 'queued';
create index jobs_running_idx on public.jobs (kind, heartbeat_at) where status = 'running';
create index jobs_created_by_idx on public.jobs (created_by);
create index jobs_document_id_idx on public.jobs ((payload ->> 'document_id'));

alter table public.jobs enable row level security;   -- no policies: backend (service key) only
revoke all on public.jobs from anon, authenticated;

-- Claim up to (max_running - running) due jobs of one kind. The advisory lock serializes claims per
-- kind, so the concurrency limit (D18) holds even with several workers; SKIP LOCKED never blocks.
create or replace function public.claim_jobs(p_kind text, p_worker text, p_max_running int default 1)
returns setof public.jobs
language plpgsql
security invoker
set search_path = public
as $$
declare
  free_slots int;
begin
  perform pg_advisory_xact_lock(hashtext('claim_jobs:' || p_kind));
  select greatest(p_max_running - count(*), 0) into free_slots
    from jobs where kind = p_kind and status = 'running';
  if free_slots = 0 then
    return;
  end if;
  return query
    update jobs j
       set status = 'running', attempts = j.attempts + 1, locked_by = p_worker,
           started_at = now(), heartbeat_at = now(), updated_at = now(), error = null
     where j.id in (
       select q.id from jobs q
        where q.kind = p_kind and q.status = 'queued' and q.run_after <= now()
        order by q.created_at
        limit free_slots
        for update skip locked)
    returning j.*;
end;
$$;

revoke execute on function public.claim_jobs(text, text, int) from public, anon, authenticated;
grant execute on function public.claim_jobs(text, text, int) to service_role;

-- ---------------------------------------------------------------- documents: soft delete
alter table public.documents
  add column deleted_at timestamptz,
  add column deleted_by uuid references public.profiles (id) on delete set null;

create index documents_deleted_by_idx on public.documents (deleted_by);

-- Swap a newly indexed version in: archive the current version of the same chain, delete its chunks
-- (no longer searchable; briefings keep their own snippet copies), make the new version current.
-- One transaction, so search never sees zero or two current versions.
create or replace function public.promote_document_version(p_new_id uuid)
returns void
language plpgsql
security invoker
set search_path = public
as $$
declare
  new_doc documents%rowtype;
begin
  select * into new_doc from documents where id = p_new_id for update;
  if not found then
    raise exception 'document % not found', p_new_id;
  end if;
  if new_doc.status <> 'indexed' or new_doc.deleted_at is not null then
    raise exception 'document % is not an indexed, live version', p_new_id;
  end if;
  if new_doc.is_current then
    return;   -- already promoted
  end if;
  if new_doc.replaces_document_id is not null then
    perform 1 from documents where id = new_doc.replaces_document_id for update;
    update documents
       set is_current = false, archived_at = now(), updated_at = now()
     where id = new_doc.replaces_document_id;
    delete from corporate_documents where document_id = new_doc.replaces_document_id;
  end if;
  update documents set is_current = true, updated_at = now() where id = p_new_id;
end;
$$;

revoke execute on function public.promote_document_version(uuid) from public, anon, authenticated;
grant execute on function public.promote_document_version(uuid) to service_role;

-- ---------------------------------------------------------------- Storage bucket (D4, D35)
-- Private. No storage.objects policies: anon/authenticated get nothing, the backend uses the service key.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('kb-documents', 'kb-documents', false, 20971520, array[
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
  'text/csv'
])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;
