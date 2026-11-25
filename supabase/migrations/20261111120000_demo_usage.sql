-- Phase 6 (D39 §2): site-wide daily cap on live research runs in the public demo.
-- One row per "demo day". The day is the Pacific date, so the cap resets together with the Gemini
-- free-tier daily quota (midnight Pacific = 10:00 Israel time in winter).
-- Backend only (service key): RLS on, no policies, functions executable by service_role only.

create table public.demo_usage (
  day        date primary key,
  runs       integer not null default 0 check (runs >= 0),
  updated_at timestamptz not null default now()
);

alter table public.demo_usage enable row level security;   -- no policies: backend (service key) only
revoke all on public.demo_usage from anon, authenticated;

create or replace function public.demo_day()
returns date
language sql
stable
set search_path = ''
as $$
  select (now() at time zone 'America/Los_Angeles')::date;
$$;

-- Atomically count one live run for today, only while today's count is below `cap`.
-- Concurrent callers serialize on the row lock of ON CONFLICT DO UPDATE, and the WHERE is re-checked
-- on the latest row version, so the cap can't be exceeded. Returns true if the run may start.
create or replace function public.claim_demo_run(cap integer)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  claimed integer;
begin
  if cap is null or cap <= 0 then
    return false;
  end if;
  insert into public.demo_usage as u (day, runs) values (public.demo_day(), 1)
  on conflict (day) do update
    set runs = u.runs + 1, updated_at = now()
    where u.runs < cap
  returning u.runs into claimed;
  return claimed is not null;
end;
$$;

create or replace function public.demo_runs_today()
returns integer
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce((select runs from public.demo_usage where day = public.demo_day()), 0);
$$;

revoke execute on function public.demo_day() from public, anon, authenticated;
revoke execute on function public.claim_demo_run(integer) from public, anon, authenticated;
revoke execute on function public.demo_runs_today() from public, anon, authenticated;
grant execute on function public.demo_day() to service_role;
grant execute on function public.claim_demo_run(integer) to service_role;
grant execute on function public.demo_runs_today() to service_role;
