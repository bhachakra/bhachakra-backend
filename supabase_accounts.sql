-- ============================================================================
-- Bhachakra: user accounts + saved charts
-- Run once in Supabase: SQL Editor > New query > paste all of this > Run.
-- Safe to run again - every step checks before it changes anything.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. PROFILES - one row per user, made automatically when they sign up.
--    (The login itself - email + password - is kept by Supabase Auth in its
--    own protected table, auth.users. This is the app's own info about them.)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id            uuid primary key references auth.users (id) on delete cascade,
  email         text,
  display_name  text,
  created_at    timestamptz not null default now(),
  last_seen_at  timestamptz
);

alter table public.profiles enable row level security;

-- each user can see and edit only their own profile
drop policy if exists "profiles: read own"   on public.profiles;
drop policy if exists "profiles: update own" on public.profiles;
drop policy if exists "profiles: insert own" on public.profiles;
create policy "profiles: read own"   on public.profiles for select using (auth.uid() = id);
create policy "profiles: update own" on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);
create policy "profiles: insert own" on public.profiles for insert with check (auth.uid() = id);

-- make the profile row automatically whenever someone signs up
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, nullif(trim(new.raw_user_meta_data ->> 'display_name'), ''))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- users who signed up before this existed get a profile too
insert into public.profiles (id, email, display_name)
select u.id, u.email, nullif(trim(u.raw_user_meta_data ->> 'display_name'), '')
from auth.users u
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- 2. SAVED CHARTS - every chart a user saves, with everything the app keeps
--    about it. An older saved_charts table (from the first backend version)
--    is NOT deleted: if it has any rows it is renamed to
--    saved_charts_backup, otherwise it is replaced.
-- ---------------------------------------------------------------------------
do $$
declare
  has_table boolean;
  has_kind  boolean;
  row_count bigint;
begin
  select exists (select 1 from information_schema.tables
                 where table_schema = 'public' and table_name = 'saved_charts') into has_table;
  if not has_table then
    return;
  end if;

  -- already the new shape? leave it alone
  select exists (select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'saved_charts' and column_name = 'kind') into has_kind;
  if has_kind then
    return;
  end if;

  execute 'select count(*) from public.saved_charts' into row_count;
  if row_count = 0 then
    drop table public.saved_charts;
  else
    alter table public.saved_charts rename to saved_charts_backup;
    raise notice 'Old saved_charts had % rows - kept as saved_charts_backup', row_count;
  end if;
end $$;

create table if not exists public.saved_charts (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name                  text not null,
  kind                  text not null default 'natal' check (kind in ('natal', 'prashna')),
  note                  text,                         -- prashna: the question / event
  date_time_iso         timestamptz not null,         -- the chart's moment
  lat                   double precision not null,
  lon                   double precision not null,
  location_name         text not null default '',
  chart_style           text,                         -- north_indian / south_indian / circular
  show_planetary_nodes  boolean,
  created_at            timestamptz not null default now(),
  last_opened_at        timestamptz
);

create index if not exists saved_charts_user_idx on public.saved_charts (user_id, created_at desc);

alter table public.saved_charts enable row level security;

-- each user can see and change only their own charts - enforced by the
-- database itself, whatever the app or backend does
drop policy if exists "charts: read own"   on public.saved_charts;
drop policy if exists "charts: insert own" on public.saved_charts;
drop policy if exists "charts: update own" on public.saved_charts;
drop policy if exists "charts: delete own" on public.saved_charts;
create policy "charts: read own"   on public.saved_charts for select using (auth.uid() = user_id);
create policy "charts: insert own" on public.saved_charts for insert with check (auth.uid() = user_id);
create policy "charts: update own" on public.saved_charts for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "charts: delete own" on public.saved_charts for delete using (auth.uid() = user_id);


-- quick check - should list both tables with rls_enabled = true
select tablename, rowsecurity as rls_enabled
from pg_tables
where schemaname = 'public' and tablename in ('profiles', 'saved_charts');
