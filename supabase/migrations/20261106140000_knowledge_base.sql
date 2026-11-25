-- Phase 2A: knowledge base core (ARCHITECTURE §6; D9, D10, D11, D33)
-- documents = one row per file version. corporate_documents = chunks.

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------- documents
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  file_name text not null,
  mime_type text,
  size_bytes bigint check (size_bytes >= 0),
  storage_path text,                       -- set by uploads (Phase 2C); null for seed files
  checksum text,                           -- sha256 of the file; unchanged file = no re-embedding
  status text not null default 'uploaded'
    check (status in ('uploaded', 'processing', 'indexed', 'failed')),
  error_message text,
  version int not null default 1 check (version >= 1),
  replaces_document_id uuid references public.documents (id) on delete set null,
  is_current boolean not null default true,
  archived_at timestamptz,
  uploaded_by uuid references public.profiles (id) on delete set null,
  indexed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- One current version per file name (ingestion is idempotent by file name).
create unique index documents_current_file_name_key on public.documents (file_name) where is_current;
create index documents_replaces_document_id_idx on public.documents (replaces_document_id);
create index documents_uploaded_by_idx on public.documents (uploaded_by);

-- ---------------------------------------------------------------- chunks
create table public.corporate_documents (
  id bigint generated always as identity primary key,
  document_id uuid not null references public.documents (id) on delete cascade,
  chunk_index int not null check (chunk_index >= 0),
  content text not null,
  -- file_name, chunk_index, section (nearest heading or CSV row range), document_id, version
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector(1536) not null,       -- D9: gemini-embedding-001 @ 1536, L2-normalized
  embedding_model text not null,
  -- D10: 'simple' config (no stemming) works for Hebrew + English; section heading is searchable too.
  fts tsvector generated always as (
    to_tsvector('simple'::regconfig, coalesce(metadata ->> 'section', '') || ' ' || content)
  ) stored,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)                -- also serves as the FK index
);

create index corporate_documents_embedding_idx on public.corporate_documents
  using hnsw (embedding extensions.vector_cosine_ops);
create index corporate_documents_fts_idx on public.corporate_documents using gin (fts);

-- ---------------------------------------------------------------- RLS
-- Reads: signed-in users see current, indexed documents (exact UI visibility decided in 2C).
-- Writes: backend only (service key) after an admin check. No write policies for API roles.
alter table public.documents enable row level security;
alter table public.corporate_documents enable row level security;

create policy "documents: read current indexed" on public.documents
  for select to authenticated using (is_current and status = 'indexed');

create policy "corporate_documents: read chunks of current indexed documents" on public.corporate_documents
  for select to authenticated using (
    exists (select 1 from public.documents d
            where d.id = document_id and d.is_current and d.status = 'indexed')
  );

revoke all on public.documents, public.corporate_documents from anon;
revoke insert, update, delete, truncate, references, trigger
  on public.documents, public.corporate_documents from authenticated;

-- ---------------------------------------------------------------- hybrid search (D10 + D11)
-- Vector (cosine) + keyword (FTS, terms OR-ed) merged with Reciprocal Rank Fusion.
-- SECURITY INVOKER: RLS applies to the caller. Only current, indexed documents are searched.
create or replace function public.hybrid_search(
  query_text text,
  query_embedding extensions.vector(1536),
  match_count int default 5,
  full_text_weight float default 1,
  semantic_weight float default 1,
  rrf_k int default 60
)
returns table (
  id bigint,
  document_id uuid,
  content text,
  metadata jsonb,
  file_name text,
  title text,
  version int,
  score float,
  semantic_rank int,
  keyword_rank int
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  with params as (
    select least(greatest(match_count, 1), 50) * 3 as pool,
           -- OR the query terms: websearch_to_tsquery ANDs every word, which with the 'simple'
           -- config (no stop words) rarely matches a natural-language question.
           (select to_tsquery('simple', string_agg(quote_literal(lexeme), ' | '))
              from unnest(to_tsvector('simple', coalesce(query_text, ''))) as t
             where length(lexeme) >= 2) as tsq
  ),
  keyword as (
    select c.id,
           row_number() over (order by ts_rank_cd(c.fts, p.tsq) desc, c.id) as rank_ix
    from corporate_documents c
    join documents d on d.id = c.document_id
    cross join params p
    where p.tsq is not null and c.fts @@ p.tsq and d.is_current and d.status = 'indexed'
    order by rank_ix
    limit (select pool from params)
  ),
  semantic as (
    select c.id,
           row_number() over (order by c.embedding <=> query_embedding, c.id) as rank_ix
    from corporate_documents c
    join documents d on d.id = c.document_id
    where d.is_current and d.status = 'indexed'
    order by c.embedding <=> query_embedding
    limit (select pool from params)
  )
  select c.id, c.document_id, c.content, c.metadata, d.file_name, d.title, d.version,
         coalesce(1.0 / (rrf_k + k.rank_ix), 0.0) * full_text_weight
           + coalesce(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight as score,
         s.rank_ix::int as semantic_rank,
         k.rank_ix::int as keyword_rank
  from keyword k
  full outer join semantic s on s.id = k.id
  join corporate_documents c on c.id = coalesce(k.id, s.id)
  join documents d on d.id = c.document_id
  order by score desc, c.id
  limit least(greatest(match_count, 1), 50);
$$;

revoke execute on function public.hybrid_search(text, extensions.vector, int, float, float, int) from public, anon;
grant execute on function public.hybrid_search(text, extensions.vector, int, float, float, int)
  to authenticated, service_role;
