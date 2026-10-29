-- Baseline for the separate cmms-pilot project. No production/demo data copied.
create schema if not exists cmms_private;
revoke all on schema cmms_private from public;
grant usage on schema cmms_private to authenticated;

create table public.cmms_members (
  user_id uuid primary key references auth.users(id),
  display_name text not null check (length(trim(display_name)) between 1 and 120),
  role text not null check (role in ('reporter','technician','manager','admin')),
  active boolean not null default true
);
create table public.cmms_assets (
  id uuid primary key default gen_random_uuid(),
  code text unique not null check (length(trim(code)) between 1 and 60),
  name text not null check (length(trim(name)) between 1 and 200),
  location text not null default '',
  created_at timestamptz not null default now()
);
create table public.cmms_jobs (
  id uuid primary key default gen_random_uuid(),
  number bigint generated always as identity unique,
  asset_id uuid not null references public.cmms_assets(id),
  reporter_id uuid not null references public.cmms_members(user_id),
  assignee_id uuid references public.cmms_members(user_id),
  symptom text not null check (length(trim(symptom)) between 1 and 5000),
  priority text not null check (priority in ('normal','urgent','critical')),
  impact text not null default '',
  status text not null default 'new' check (status in ('new','assigned','repairing','waiting_parts','acceptance','closed','cancelled')),
  due_date date,
  cause text not null default '', repair text not null default '', parts text not null default '',
  labor_minutes integer not null default 0 check (labor_minutes >= 0),
  downtime_minutes integer not null default 0 check (downtime_minutes >= 0),
  version integer not null default 1,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index on public.cmms_jobs(reporter_id);
create index on public.cmms_jobs(assignee_id);
create index on public.cmms_jobs(asset_id);
create index on public.cmms_jobs(status,created_at desc);
create table public.cmms_events (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.cmms_jobs(id),
  actor_id uuid not null references public.cmms_members(user_id),
  action text not null, note text not null default '',
  created_at timestamptz not null default now()
);
create index on public.cmms_events(job_id,created_at);
create index on public.cmms_events(actor_id);
create table public.cmms_pm (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.cmms_assets(id),
  task text not null check(length(trim(task)) between 1 and 2000),
  assignee_id uuid not null references public.cmms_members(user_id),
  due_date date not null,
  frequency text not null check(frequency in ('daily','weekly','monthly','yearly')),
  result text not null default '', completed_at timestamptz,
  completed_by uuid references public.cmms_members(user_id),
  created_at timestamptz not null default now()
);
create index on public.cmms_pm(assignee_id,due_date);
create index on public.cmms_pm(asset_id);
create index on public.cmms_pm(completed_by);

create function cmms_private.member_role() returns text
language sql stable security definer set search_path = '' as $$
  select m.role from public.cmms_members m where m.user_id = auth.uid() and m.active and auth.uid() is not null
$$;
revoke all on function cmms_private.member_role() from public,anon;
grant execute on function cmms_private.member_role() to authenticated;

alter table public.cmms_members enable row level security;
alter table public.cmms_assets enable row level security;
alter table public.cmms_jobs enable row level security;
alter table public.cmms_events enable row level security;
alter table public.cmms_pm enable row level security;
revoke all on public.cmms_members, public.cmms_assets, public.cmms_jobs, public.cmms_events, public.cmms_pm from anon,authenticated;
grant select on public.cmms_members, public.cmms_assets, public.cmms_jobs, public.cmms_events, public.cmms_pm to authenticated;

create policy members_read on public.cmms_members for select to authenticated using (
 user_id = (select auth.uid()) or (select cmms_private.member_role()) in ('manager','admin')
);
create policy assets_read on public.cmms_assets for select to authenticated using ((select cmms_private.member_role()) is not null);
create policy jobs_read on public.cmms_jobs for select to authenticated using (
 (select cmms_private.member_role()) is not null and
 (reporter_id = (select auth.uid()) or assignee_id = (select auth.uid()) or (select cmms_private.member_role()) in ('manager','admin'))
);
create policy events_read on public.cmms_events for select to authenticated using (
 exists(select 1 from public.cmms_jobs j where j.id = job_id)
);
create policy pm_read on public.cmms_pm for select to authenticated using (
 (select cmms_private.member_role()) is not null and
 (assignee_id = (select auth.uid()) or (select cmms_private.member_role()) in ('manager','admin'))
);

-- All mutations go through a single guarded transaction. Client cannot choose actor,
-- reporter, timestamps, version or arbitrary columns. Row locks prevent lost updates.
create function cmms_private.command(p_action text, p_data jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
 uid uuid := auth.uid(); r text; j public.cmms_jobs; p public.cmms_pm;
 target uuid; msg text := trim(coalesce(p_data->>'note','')); newstate text;
begin
 r := cmms_private.member_role();
 if uid is null or r is null then raise exception 'CMMS_ACCESS_DENIED' using errcode='42501'; end if;
 if p_action = 'asset_create' then
   if r not in ('manager','admin') then raise exception 'CMMS_ACCESS_DENIED'; end if;
   insert into public.cmms_assets(code,name,location) values (upper(trim(p_data->>'code')),trim(p_data->>'name'),coalesce(trim(p_data->>'location'),'')) returning id into target;
   return jsonb_build_object('id',target);
 elsif p_action = 'member_save' then
   if r <> 'admin' then raise exception 'CMMS_ACCESS_DENIED'; end if;
   target := (p_data->>'user_id')::uuid;
   -- Never permit the currently signed-in admin to demote/disable themself.
   if target = uid and (p_data->>'role' <> 'admin' or not (p_data->>'active')::boolean) then raise exception 'CMMS_KEEP_OWN_ADMIN'; end if;
   insert into public.cmms_members(user_id,display_name,role,active)
   values(target,trim(p_data->>'display_name'),p_data->>'role',(p_data->>'active')::boolean)
   on conflict(user_id) do update set display_name=excluded.display_name,role=excluded.role,active=excluded.active;
   return jsonb_build_object('id',target);
 elsif p_action = 'job_create' then
   insert into public.cmms_jobs(asset_id,reporter_id,symptom,priority,impact)
   values((p_data->>'asset_id')::uuid,uid,trim(p_data->>'symptom'),p_data->>'priority',coalesce(p_data->>'impact','')) returning * into j;
   insert into public.cmms_events(job_id,actor_id,action) values(j.id,uid,'new');
   return jsonb_build_object('id',j.id,'number',j.number);
 elsif p_action = 'pm_create' then
   if r not in ('manager','admin') then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if not exists(select 1 from public.cmms_members where user_id=(p_data->>'assignee_id')::uuid and active and role='technician') then raise exception 'CMMS_INVALID_TECHNICIAN'; end if;
   insert into public.cmms_pm(asset_id,task,assignee_id,due_date,frequency)
   values((p_data->>'asset_id')::uuid,trim(p_data->>'task'),(p_data->>'assignee_id')::uuid,(p_data->>'due_date')::date,p_data->>'frequency') returning id into target;
   return jsonb_build_object('id',target);
 elsif p_action = 'pm_complete' then
   select * into p from public.cmms_pm where id=(p_data->>'id')::uuid for update;
   if not found or p.assignee_id<>uid or r<>'technician' or p.completed_at is not null then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if msg = '' then raise exception 'CMMS_NOTE_REQUIRED'; end if;
   update public.cmms_pm set result=msg,completed_at=now(),completed_by=uid where id=p.id;
   return jsonb_build_object('id',p.id);
 end if;
 select * into j from public.cmms_jobs where id=(p_data->>'id')::uuid for update;
 if not found then raise exception 'CMMS_NOT_FOUND'; end if;
 if j.version <> coalesce((p_data->>'version')::integer,0) then raise exception 'CMMS_STALE_VERSION'; end if;
 if p_action = 'assign' then
   if r not in ('manager','admin') or j.status not in ('new','assigned') then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if not exists(select 1 from public.cmms_members where user_id=(p_data->>'assignee_id')::uuid and active and role='technician') then raise exception 'CMMS_INVALID_TECHNICIAN'; end if;
   update public.cmms_jobs set assignee_id=(p_data->>'assignee_id')::uuid,due_date=(p_data->>'due_date')::date,priority=p_data->>'priority',status='assigned' where id=j.id;
 elsif p_action = 'start' then
   if r <> 'technician' or j.assignee_id is distinct from uid or j.status not in ('assigned','waiting_parts') then raise exception 'CMMS_ACCESS_DENIED'; end if;
   update public.cmms_jobs set status='repairing' where id=j.id;
 elsif p_action in ('progress','wait_parts','submit') then
   if r <> 'technician' or j.assignee_id is distinct from uid or j.status<>'repairing' then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if p_action='submit' and (trim(coalesce(p_data->>'cause',''))='' or trim(coalesce(p_data->>'repair',''))='') then raise exception 'CMMS_REPAIR_REQUIRED'; end if;
   if p_action='wait_parts' and trim(coalesce(p_data->>'parts',''))='' then raise exception 'CMMS_PARTS_REQUIRED'; end if;
   newstate := case p_action when 'submit' then 'acceptance' when 'wait_parts' then 'waiting_parts' else 'repairing' end;
   update public.cmms_jobs set cause=coalesce(p_data->>'cause',''),repair=coalesce(p_data->>'repair',''),parts=coalesce(p_data->>'parts',''),labor_minutes=(p_data->>'labor_minutes')::integer,downtime_minutes=(p_data->>'downtime_minutes')::integer,status=newstate where id=j.id;
 elsif p_action in ('accept','reject') then
   if j.status<>'acceptance' or not (j.reporter_id=uid or r in ('manager','admin')) then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if msg='' then raise exception 'CMMS_NOTE_REQUIRED'; end if;
   update public.cmms_jobs set status=case p_action when 'accept' then 'closed' else 'repairing' end where id=j.id;
 elsif p_action='cancel' then
   if r not in ('manager','admin') or j.status in ('closed','cancelled') then raise exception 'CMMS_ACCESS_DENIED'; end if;
   if msg='' then raise exception 'CMMS_NOTE_REQUIRED'; end if;
   update public.cmms_jobs set status='cancelled' where id=j.id;
 else raise exception 'CMMS_INVALID_ACTION';
 end if;
 update public.cmms_jobs set version=version+1,updated_at=now() where id=j.id;
 insert into public.cmms_events(job_id,actor_id,action,note) values(j.id,uid,p_action,msg);
 return jsonb_build_object('id',j.id);
end $$;
revoke all on function cmms_private.command(text,jsonb) from public,anon;
grant execute on function cmms_private.command(text,jsonb) to authenticated;
create function public.cmms_command(p_action text,p_data jsonb) returns jsonb
language sql security invoker set search_path = '' as $$ select cmms_private.command(p_action,p_data) $$;
revoke all on function public.cmms_command(text,jsonb) from public,anon;
grant execute on function public.cmms_command(text,jsonb) to authenticated;

-- Private attachments: read access follows job visibility; upload allowed to the
-- reporter or assigned technician only while the job is open. No overwrite/delete.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('cmms-photos','cmms-photos',false,5242880,array['image/jpeg','image/png']);
create policy cmms_photos_read on storage.objects for select to authenticated using (
 bucket_id='cmms-photos' and exists(select 1 from public.cmms_jobs j where j.id::text=(storage.foldername(name))[1])
);
create policy cmms_photos_insert on storage.objects for insert to authenticated with check (
 bucket_id='cmms-photos' and (select cmms_private.member_role()) is not null and
 exists(select 1 from public.cmms_jobs j where j.id::text=(storage.foldername(name))[1]
 and j.status not in ('closed','cancelled') and (j.reporter_id=(select auth.uid()) or j.assignee_id=(select auth.uid())))
);

