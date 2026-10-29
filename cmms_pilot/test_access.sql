-- Transaction-only fixtures: no users or maintenance data remain after this test.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-4000-a000-000000000001','cmms-admin@example.invalid'),
 ('00000000-0000-4000-a000-000000000002','cmms-manager@example.invalid'),
 ('00000000-0000-4000-a000-000000000003','cmms-tech-a@example.invalid'),
 ('00000000-0000-4000-a000-000000000004','cmms-tech-b@example.invalid'),
 ('00000000-0000-4000-a000-000000000005','cmms-reporter-a@example.invalid'),
 ('00000000-0000-4000-a000-000000000006','cmms-reporter-b@example.invalid'),
 ('00000000-0000-4000-a000-000000000007','cmms-unapproved@example.invalid');
insert into public.cmms_members(user_id,display_name,role) values
 ('00000000-0000-4000-a000-000000000001','Test Admin','admin'),
 ('00000000-0000-4000-a000-000000000002','Test Manager','manager'),
 ('00000000-0000-4000-a000-000000000003','Test Tech A','technician'),
 ('00000000-0000-4000-a000-000000000004','Test Tech B','technician'),
 ('00000000-0000-4000-a000-000000000005','Test Reporter A','reporter'),
 ('00000000-0000-4000-a000-000000000006','Test Reporter B','reporter');
create function pg_temp.assert_true(v boolean,msg text) returns void language plpgsql as $$
begin if v is distinct from true then raise exception 'TEST FAILED: %',msg; end if; end $$;
create function pg_temp.expect_error(q text,pattern text) returns void language plpgsql as $$
begin
 begin execute q; exception when others then
   if sqlerrm like '%'||pattern||'%' then return; end if;
   raise;
 end;
 raise exception 'TEST FAILED: expected %',pattern;
end $$;
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000002","role":"authenticated"}',true);
select set_config('cmms.test_asset',(public.cmms_command('asset_create','{"code":"TEST-ONLY","name":"Test asset","location":"Test"}')->>'id'),true);
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000005","role":"authenticated"}',true);
select set_config('cmms.test_job',(public.cmms_command('job_create',jsonb_build_object('asset_id',current_setting('cmms.test_asset'),'symptom','Test only','priority','normal'))->>'id'),true);
select pg_temp.assert_true((select count(*)=1 from public.cmms_jobs),'reporter sees own job');
select pg_temp.expect_error($q$select public.cmms_command('member_save','{"user_id":"00000000-0000-4000-a000-000000000005","role":"admin","display_name":"Escalation","active":true}')$q$,'CMMS_ACCESS_DENIED');
select pg_temp.expect_error('update public.cmms_jobs set status=''closed''','permission denied');
insert into storage.objects(bucket_id,name) values('cmms-photos',current_setting('cmms.test_job')||'/test.jpg');
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000006","role":"authenticated"}',true);
select pg_temp.assert_true((select count(*)=0 from public.cmms_jobs),'other reporter cannot read job');
select pg_temp.assert_true((select count(*)=0 from public.cmms_events),'other reporter cannot read audit');
select pg_temp.assert_true((select count(*)=0 from storage.objects where bucket_id='cmms-photos'),'other reporter cannot read photo');
select pg_temp.expect_error($q$select public.cmms_command('assign',jsonb_build_object('id',current_setting('cmms.test_job'),'version',1))$q$,'CMMS_ACCESS_DENIED');
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000002","role":"authenticated"}',true);
select public.cmms_command('assign',jsonb_build_object('id',current_setting('cmms.test_job'),'version',1,'assignee_id','00000000-0000-4000-a000-000000000003','due_date',current_date,'priority','urgent'));
select pg_temp.expect_error($q$select public.cmms_command('assign',jsonb_build_object('id',current_setting('cmms.test_job'),'version',1))$q$,'CMMS_STALE_VERSION');
select set_config('cmms.test_pm',(public.cmms_command('pm_create',jsonb_build_object('asset_id',current_setting('cmms.test_asset'),'task','Test inspection','assignee_id','00000000-0000-4000-a000-000000000003','due_date',current_date,'frequency','monthly'))->>'id'),true);
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000004","role":"authenticated"}',true);
select pg_temp.assert_true((select count(*)=0 from public.cmms_jobs),'unassigned tech cannot see job');
select pg_temp.expect_error($q$select public.cmms_command('start',jsonb_build_object('id',current_setting('cmms.test_job'),'version',2))$q$,'CMMS_ACCESS_DENIED');
select pg_temp.expect_error($q$select public.cmms_command('pm_complete',jsonb_build_object('id',current_setting('cmms.test_pm'),'note','test'))$q$,'CMMS_ACCESS_DENIED');
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000003","role":"authenticated"}',true);
select pg_temp.assert_true((select count(*)=1 from public.cmms_jobs),'assigned tech sees job');
select public.cmms_command('start',jsonb_build_object('id',current_setting('cmms.test_job'),'version',2));
select pg_temp.expect_error($q$select public.cmms_command('submit',jsonb_build_object('id',current_setting('cmms.test_job'),'version',3))$q$,'CMMS_REPAIR_REQUIRED');
select public.cmms_command('wait_parts',jsonb_build_object('id',current_setting('cmms.test_job'),'version',3,'parts','Test belt','cause','Test','repair','Test','labor_minutes',5,'downtime_minutes',10));
select public.cmms_command('start',jsonb_build_object('id',current_setting('cmms.test_job'),'version',4));
select public.cmms_command('submit',jsonb_build_object('id',current_setting('cmms.test_job'),'version',5,'parts','Test belt','cause','Test cause','repair','Test repair','labor_minutes',10,'downtime_minutes',20));
select public.cmms_command('pm_complete',jsonb_build_object('id',current_setting('cmms.test_pm'),'note','Test passed'));
select pg_temp.expect_error($q$select public.cmms_command('pm_complete',jsonb_build_object('id',current_setting('cmms.test_pm'),'note','Test'))$q$,'CMMS_ACCESS_DENIED');
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000005","role":"authenticated"}',true);
select public.cmms_command('reject',jsonb_build_object('id',current_setting('cmms.test_job'),'version',6,'note','Test rework'));
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000003","role":"authenticated"}',true);
select public.cmms_command('submit',jsonb_build_object('id',current_setting('cmms.test_job'),'version',7,'parts','Test belt','cause','Test cause','repair','Test fixed','labor_minutes',15,'downtime_minutes',25));
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000005","role":"authenticated"}',true);
select public.cmms_command('accept',jsonb_build_object('id',current_setting('cmms.test_job'),'version',8,'note','Test accepted'));
select pg_temp.assert_true((select status='closed' and version=9 from public.cmms_jobs where id=current_setting('cmms.test_job')::uuid),'job closed');
select pg_temp.assert_true((select count(*)=9 from public.cmms_events where job_id=current_setting('cmms.test_job')::uuid),'all changes audited');
select pg_temp.expect_error($q$insert into storage.objects(bucket_id,name) values('cmms-photos',current_setting('cmms.test_job')||'/closed.jpg')$q$,'row-level security');
select set_config('request.jwt.claims','{"sub":"00000000-0000-4000-a000-000000000007","role":"authenticated"}',true);
select pg_temp.assert_true((select count(*)=0 from public.cmms_assets),'unapproved user cannot see assets');
select pg_temp.expect_error($q$select public.cmms_command('asset_create','{}')$q$,'CMMS_ACCESS_DENIED');
reset role;
select 'PASS: RLS isolation, no role escalation, private photos, workflow, concurrency, PM, audit' as result;
rollback;

