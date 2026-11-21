# Identity-only launch — November 6, 2026

The launch build defaults to `GOOGLE_INTEGRATIONS_ENABLED=false`. It requests only `openid`, `email`, and `profile` during Google sign-in. Invitations and Google identity links still identify fellows, independently of the separate staff username/password sessions.

## What is available

- Invitation enrollment and returning Google sign-in using personal Google accounts.
- Coordinator Drive resources for all or selected cohorts, fellow pins, confirmed meetings and upcoming or overdue deadlines. Run `python manage.py migrate --noinput` through `0017_fellowship_catalog` and `python manage.py setup_staff_group` before deploying the updated dashboard.
- Staff administration, cohorts, phase catalog, individual and shared-team assignments.
- Manual WhenBound selection, submission and group availability, including linked assignment completion.
- Badges, SDGs, dashboard progress and personalization.
- Reminder previews using the existing console backend. These are not delivered to inboxes.

## Deferred integrations

- Google Drive browsing, folder selection, search and automatic shared workspace documents.
- Google Calendar event lists, Next Up, availability import and calendar conflict overlays.
- Google Tasks import/API access and assignment mirroring.

The dashboard omits the related controls and background requests. Authenticated direct requests to deferred endpoints receive HTTP 403 with `code: google_integrations_disabled`. The credential helper also refuses access, so previously saved API tokens cannot bypass the setting. Tokens already stored in an existing database are not deleted or revoked. New tokens are not persisted in launch mode. User identity links and UNbound data remain intact.

## Google setup before public sign-in

1. Confirm the Google Cloud project and Web OAuth client belong to the intended UNbound owner. Keep client ID/secret in Azure environment settings, not Git.
2. In Google Auth Platform Data Access, configure only `openid`, `.../auth/userinfo.email` and `.../auth/userinfo.profile`. Remove Calendar, Drive and Tasks scopes for this launch. The code uses the equivalent `email` and `profile` aliases. Check with the owner before changing a Cloud project shared with another app.
3. Set the exact authorized redirect URI to `https://YOUR-HOST/accounts/google/login/callback/`, including the trailing slash. Use the same host users will visit. Configure a custom domain callback too if using it.
4. Review Audience and publishing status for an external production app. Review Branding, support contact, authorized domains and any public homepage/privacy URLs or brand verification requested by Google. Identity-only access avoids sensitive/restricted-scope verification; it does not bypass OAuth client setup or brand verification requirements.
5. Test a newly invited account and a returning account on the actual HTTPS host. The consent request should contain only basic identity permissions. Use a new test account or review previous grants when checking consent, since changing scopes does not revoke historical Google permissions.

Official references: [Google identity setup](https://developers.google.com/identity/openid-connect/openid-connect), [Google verification requirements](https://support.google.com/cloud/answer/13463073?hl=en).

## Azure release checklist

Follow [DEPLOYMENT.md](DEPLOYMENT.md) for all environment variables and PostgreSQL setup. In particular:

```text
GOOGLE_INTEGRATIONS_ENABLED=false
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DJANGO_DEBUG=false
```

Deploy `backend/` as the app root with Python 3.14 and its pinned requirements. Back up any existing database, run migrations once, create/configure staff accounts, run `setup_staff_group`, collect static files and run `check --deploy`. Start with `sh start.sh`. Configure HTTPS, database connectivity/backups, exact allowed hosts and trusted origins, public site URL, secrets and cost alerts. Do not import the divergent old SQLite database without reconciliation.

Before inviting fellows, verify on Azure:

- First enrollment consumes one invitation and assigns the intended cohort. Returning login needs no new code.
- Staff login/logout and fellow login/logout remain independent, including in the same browser.
- Staff can assign individual/team tasks and a meeting poll. Fellows can complete tasks and submit availability. Other cohorts cannot access them.
- Completing a team task updates the shared completion. All-busy availability counts as submitted.
- Open Google Drive in the dashboard. Check that links belong to the signed-in fellow’s cohort, open in Drive, and trigger no Google data API requests from UNbound. Check badges, progress, SDGs and colors.
- Reminder previews remain console-only. Platform logs must not capture OAuth authorization query strings. App Service/Application Insights logging must be reviewed separately from Gunicorn.

Local tests use synthetic SQLite data and mocked OAuth responses. They do not establish live Google consent, Azure startup, or PostgreSQL behavior. Those remain deployment acceptance checks.

## Accessing the previous complete version

The exact pre-deferral build is preserved by Git tag **`full-google-integrations-2026-11-06`**, pointing at commit **`11dcb0ee8247a2393a5046d1004321aabe9e0a65`**. GitHub branch `testing/backend` retains that full-feature build. Branch `basic-launch` contains the deferred-integration launch build. The preservation tag is published alongside these branches.

A complete source ZIP was also created outside the checkout at:

`/Users/mauricio/Documents/UNbound 2/UNbound-full-integrations-2026-11-06.zip`

Unzip it into a separate directory to inspect/run the old complete build without replacing the launch checkout. The archive contains tracked source and documentation, not `.env`, OAuth secrets, a virtual environment or the local database. Use separate local settings and a separate database when testing it. The tag can recreate that source archive from the repository root:

```sh
git archive --format=zip --prefix=UNbound-full-integrations/ --output=../UNbound-full-integrations.zip full-google-integrations-2026-11-06
```

For later restoration within the newer build, keep the newer code and deliberately set `GOOGLE_INTEGRATIONS_ENABLED=true`, then restart the app. This restores the prior integration UI, data scopes, offline consent and token storage. Do this only after preparing Google Data Access, enabling the relevant APIs and completing applicable verification. Fellows who enrolled in launch mode must authorize the additional scopes by signing out of the portal and signing in again. Historical tokens may have expired or insufficient permissions; do not treat the switch as a substitute for live integration acceptance tests.
