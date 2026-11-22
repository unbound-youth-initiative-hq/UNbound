# Delivery build

Delivery target: the GitHub `basic-launch` branch. The complete Google-integrated version is retained on `testing/backend`. This checkout contains the identity-only launch configuration. See [LAUNCH.md](LAUNCH.md) for Google setup, deferred features, acceptance checks and access to the previous complete build.

## Local setup

From `backend/`, create a Python 3.14 environment and install `requirements.txt`. Copy `.env.example` to `.env` and fill Google credentials locally. Run `python manage.py migrate`, `python manage.py createsuperuser`, `python manage.py setup_staff_group`, then `python manage.py runserver`.

The old checkout and its SQLite database were deliberately preserved. This delivery checkout starts without account data or credentials.

## Azure App Service

Deploy the contents of `backend/` as the app root. Use a supported Python 3.14 runtime and install requirements. Configure:

- DJANGO_DEBUG=false
- DJANGO_SECRET_KEY: newly generated, private, at least 50 characters
- DJANGO_ALLOWED_HOSTS: comma-separated exact public hostnames
- DJANGO_CSRF_TRUSTED_ORIGINS: HTTPS origins
- DJANGO_TRUST_PROXY_HEADERS=true only on Azure's trusted proxy
- DATABASE_URL: PostgreSQL URL; percent-encode credentials; SSL required by default
- SITE_BASE_URL: the public HTTPS URL
- GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
- GOOGLE_INTEGRATIONS_ENABLED=false (the default). Calendar, Drive and Google Tasks are deferred. GOOGLE_SHARED_WORKSPACE_EMAIL is unused in this mode.
- EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend until real sending is separately approved

After a database backup, run migrations as one release step, then `collectstatic --noinput` and `check --deploy`. Startup command: `sh start.sh`. Do not migrate from each worker. Enable HTTPS Only in Azure. Django intentionally leaves HSTS include-subdomains and preloading off until domain ownership/TLS coverage is confirmed. This produces W005/W021 from check --deploy; enable DJANGO_HSTS_INCLUDE_SUBDOMAINS and DJANGO_HSTS_PRELOAD only after reviewing all subdomains and the preload requirements. Register the exact public HTTPS Google OAuth callback ending in `/accounts/google/login/callback/`. Configure Google Auth Platform Data Access for identity scopes only (`openid`, email, profile), remove Calendar/Drive/Tasks scopes from the launch project configuration, and review Branding/Audience before releasing. Basic sign-in does not require sensitive/restricted-scope verification, but branding requirements are separate. See LAUNCH.md. The app no longer requests offline access or stores new Google API tokens in launch mode. Old tokens are left intact but cannot be used by the disabled integrations. Production configuration fails early for missing secrets, hostnames or PostgreSQL URL.

Coordinators send task drafts from their own mail app. This workflow requires no mail server or scheduled worker. For deployments using the separate reminder delivery queue, `python manage.py send_pending_reminders` processes queued deliveries. Review failed or uncertain deliveries before manually requeuing them.

WhiteNoise serves collected static assets. Coordinator-uploaded badge icons are resized and stored in PostgreSQL. The bundled badge sheet and favicons ship with the static files. Retain database backups, restrict its network access, and establish monitoring/cost alerts in the actual subscription. Gunicorn access logs omit query strings and referrers to avoid logging OAuth codes. Check Azure platform logs and Application Insights separately for query-string capture before using real accounts.

## Favicon on Render

1. The portal already includes the UNbound favicon. To replace it, commit square PNGs with the same names at `backend/static/favicon-light.png` and `backend/static/favicon-dark.png`. The dark version is used when the browser prefers dark mode.
2. Merge the changes into `basic-launch`. The Render web service uses `backend/` as its root. Keep `python manage.py collectstatic --noinput` and `python manage.py migrate --noinput` in the existing build command.
3. If auto-deploy is off, open **UNbound → Manual Deploy → Deploy latest commit** in Render. After the service reports **Live**, open `/favicon.ico` on the service URL to check the image. A private tab can help if the browser still shows its cached tab icon. [Render deployment controls](https://render.com/docs/deploys)

## Fellowship catalog update

Migration `0017_fellowship_catalog` replaces the demo badges with the 12 coordinator-awarded milestones and resets earned badges and XP. Restoring the old awards requires a pre-deployment database backup. It migrates cohort assignments to Launchpad (Orbit of Ideas), Lift-off (Launch Sequence and Mission Build), or Orbit (Trajectory, Touchdown and Graduation). Custom phase names stay available.

In **Admin → Badges**, choose a badge and select its artwork, or upload a PNG, JPEG or WebP. An uploaded icon takes priority. In **Admin → Fellows**, open a fellow and mark the appropriate badge **Earned**.

## Task email drafts

Open **Admin → Tasks**. With no rows selected, choose **Email about overdue tasks**. Check specific rows to switch to **Email about selected tasks**. Personal work produces one draft per fellow and shared team work produces one draft per cohort. For recipient rules, permissions, editing, and sending, see the [coordinator instructions](OPERATIONS.md#task-email-drafts).

## Data preservation

Migration 0011 converts existing cohort phase strings to catalog entries, including custom names, before removing the old column. It backfills submission records for completed meeting assignments with saved slots. No data from a different checkout is automatically copied.

An older database preceding migration 0005 needs a reviewed export of its Fellow project/phase fields BEFORE upgrading: the historical 0005 migration removes those fields. The divergent local copy also has different 0002/0003 migrations. Do not attach that SQLite database, fake migration history or reset it. Reconcile an export into a backup/staging database first.

## Validation

`python manage.py test fellows --settings=unbound.test_settings` uses an in-memory SQLite database and mocked/no external delivery. PostgreSQL deployment and live Google integration still require staging verification. Unit tests are not a substitute for that release check.

## Beta backup and release

Assign two recovery owners before rolling out to fellows. During active fellowship periods, export an encrypted PostgreSQL backup daily and again before migrations. Follow the [Supabase logical backup and restore guide](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore) using an authorized operator connection. Store the encrypted backup in organization-controlled storage, keep keys separately, and verify a test restore monthly. Confirm counts and sample relationships for cohorts, identities, invitations, tasks, WhenBound responses, badge awards, reminders and resources. Use an isolated database and keep email delivery disabled during the rehearsal.

The external resources migration adds descriptive fields and retains database defaults for inserts by an older instance. The SDG migration fills missing goals and preserves edited labels. Run both on a PostgreSQL copy before production. After switching traffic, verify login, an existing task, a WhenBound response, an awarded badge and one shared resource visible to its intended cohort. If resources have been unpublished from a cohort form, recover by deploying a compatible fix. An older release predating cohort publication status would display those links again. Never reverse migrations as part of a routine application rollback.

Run synthetic traffic at 5, 20 and 60 concurrent fellows before widening enrollment. Measure warm dashboard and task latency, shared completion, poll submission correctness, CPU, memory and database connections. Compare warm p95 against 2 seconds at 20 and 5 seconds at 60. Check Supabase database size, egress and last good backup. Keep the current single-worker Render process while those measurements are within budget.

References: https://learn.microsoft.com/en-us/azure/app-service/configure-language-python and https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/
