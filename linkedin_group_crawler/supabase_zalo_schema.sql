create extension if not exists pgcrypto;

create table if not exists public.zalo_users (
  user_id text primary key,
  display_name text,
  zalo_status text not null default 'unknown',
  last_login_at timestamptz,
  last_seen_at timestamptz,
  assigned_worker_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.zalo_crawl_jobs (
  job_id text primary key,
  user_id text not null,
  group_id text,
  group_name text not null,
  status text not null default 'queued',
  messages_collected integer not null default 0,
  images_found integer not null default 0,
  oldest_message_date text,
  started_at timestamptz,
  completed_at timestamptz,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.zalo_groups (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  group_id text not null,
  group_name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, group_id)
);

create table if not exists public.zalo_messages (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  job_id text references public.zalo_crawl_jobs(job_id) on delete set null,
  group_id text,
  group_name text,
  source_message_id text,
  sender_id text,
  sender_name text,
  timestamp_text text,
  time_text text,
  type text not null default 'text',
  content text,
  is_sent boolean not null default false,
  is_deleted boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, group_id, source_message_id)
);

create table if not exists public.zalo_message_assets (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.zalo_messages(id) on delete cascade,
  source_url text,
  storage_path text,
  storage_url text,
  status text not null default 'pending',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (message_id, source_url)
);

create table if not exists public.zalo_broadcast_campaigns (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  status text not null default 'queued',
  content_mode text not null default 'both',
  message_count integer not null default 0,
  target_count integer not null default 0,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.zalo_broadcast_targets (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references public.zalo_broadcast_campaigns(id) on delete cascade,
  group_id text,
  group_name text not null,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.zalo_broadcast_items (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references public.zalo_broadcast_campaigns(id) on delete cascade,
  message_id uuid not null references public.zalo_messages(id) on delete cascade,
  position integer not null default 0,
  status text not null default 'queued',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.zalo_broadcast_logs (
  id uuid primary key default gen_random_uuid(),
  campaign_id uuid not null references public.zalo_broadcast_campaigns(id) on delete cascade,
  group_name text not null default '',
  message_id uuid references public.zalo_messages(id) on delete set null,
  status text not null,
  detail text,
  created_at timestamptz not null default now()
);

create index if not exists idx_zalo_messages_user_group on public.zalo_messages(user_id, group_name);
create index if not exists idx_zalo_messages_created_at on public.zalo_messages(created_at desc);
create index if not exists idx_zalo_message_assets_cleanup on public.zalo_message_assets(status, created_at);
create index if not exists idx_zalo_broadcast_logs_campaign on public.zalo_broadcast_logs(campaign_id, created_at);
