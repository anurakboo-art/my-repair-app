# CMMS pilot

Separate authenticated pilot; the existing public session demo remains independent.

## Deployment

Streamlit entry point: `cmms_pilot/app.py`.
Install exact versions from `requirements.txt`; `requirements-lock.txt` records the full tested environment.
`public_config.json` contains only the Supabase URL and **publishable** key. No service-role/admin key is used by this app.

Database baseline is in `schema.sql`, already applied to the separate `cmms-pilot` project.
Database tests in `test_access.sql` use transaction-only synthetic users and finish with ROLLBACK.
Never apply the baseline to an existing populated project without review.

## First administrator

1. Register through the app and verify the email.
2. Sign in; the pending-approval screen displays the authenticated user's UUID.
3. The project owner verifies the intended administrator's UUID/email in Supabase Auth.
4. In Supabase SQL Editor, add the verified UUID to `cmms_members` with role `admin`, an appropriate display_name and active=true. Do not auto-promote the first registrant.
5. That administrator can approve further registered accounts from the Users page. Users cannot self-assign roles.

Example (replace only with an explicitly verified UUID/name):
```sql
insert into public.cmms_members(user_id,display_name,role,active)
values ('VERIFIED-AUTH-UUID'::uuid,'Verified administrator','admin',true);
```

Auth sessions live only in the individual Streamlit session. Reload/new session may require signing in again; maintenance records and photos persist in Supabase. Do not cache authenticated clients globally.
Configure the Supabase Auth Site URL and allowed redirect URL to the final pilot URL before email onboarding.
Passwords are entered by users; do not commit them or send them in chat.

## Access model

- Approved members read the asset register.
- Reporters read their own jobs; technicians also read assigned jobs; managers/admins read all jobs.
- Audit and private photo access follow the job visibility policy.
- Only manager/admin roles create assets, assign work or create PM tasks.
- Only assigned technicians record repair results or complete PM.
- Reporter or manager/admin accepts/rejects completed repairs.
- Only admins approve/disable accounts. Database command function validates roles on every mutation.
- All job changes are atomic, version checked and audited with server-derived actor/time.

## Scope

Included: login/registration/approval, persistent assets/jobs/PM, private photos, repair workflow, row-level authorization, audit, optimistic concurrency and CSV export.
Not yet included: password-recovery UI, MFA, automatic recurring PM, inventory, notifications, backup automation or restore drill. Before real maintenance use, configure backup/export and verify restore plus onboarding/recovery with actual authorized pilot users.

