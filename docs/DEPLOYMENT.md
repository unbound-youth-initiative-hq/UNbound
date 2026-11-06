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

When enabling real email, schedule `python manage.py send_pending_reminders` as a recurring worker job (one process per run). The Admin action queues deliveries; it does not send SMTP inside the web request. Console previews are processed immediately. Review failed/uncertain deliveries before any manual requeue.

WhiteNoise serves collected static assets. User-uploaded badge images are not yet supported by this build; add persistent storage before enabling them. Retain database backups, restrict its network access, and establish monitoring/cost alerts in the actual subscription. Gunicorn access logs omit query strings and referrers to avoid logging OAuth codes. Check Azure platform logs and Application Insights separately for query-string capture before using real accounts.

## Data preservation

Migration 0011 converts existing cohort phase strings to catalog entries, including custom names, before removing the old column. It backfills submission records for completed meeting assignments with saved slots. No data from a different checkout is automatically copied.

An older database preceding migration 0005 needs a reviewed export of its Fellow project/phase fields BEFORE upgrading: the historical 0005 migration removes those fields. The divergent local copy also has different 0002/0003 migrations. Do not attach that SQLite database, fake migration history or reset it. Reconcile an export into a backup/staging database first.

## Validation

`python manage.py test fellows --settings=unbound.test_settings` uses an in-memory SQLite database and mocked/no external delivery. PostgreSQL deployment and live Google integration still require staging verification. Unit tests are not a substitute for that release check.

References: https://learn.microsoft.com/en-us/azure/app-service/configure-language-python and https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/
