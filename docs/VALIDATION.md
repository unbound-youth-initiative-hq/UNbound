# Validation record — October 29, 2026

Latest session isolation follow-up: **67 Django tests and 10 frontend tests pass**. Admin and portal cookies and CSRF secrets are independent. Eight browser-like tests enforce CSRF while checking both login orders, independent logout, cookie scope and token misuse rejection; four additional tests use actual Admin forms and the dashboard's CSRF meta/header flow. Twelve OAuth callback tests cover invitation enrollment and persistent Google identity without automatic staff enrollment or email-based account fusion. The live local Admin form was also opened in a background browser and submitted with deliberately invalid synthetic credentials: it returned the normal credential error, confirming CSRF validation succeeded. No real user credentials were submitted through that browser check.

The earlier shared-session preservation workaround below has been superseded by separate sessions. No schema migration or live-account repair was needed for this change.

Authentication follow-up: 53 Django tests now pass, including 10 additional real allauth state/callback integration tests with mocked Google token/identity responses. These cover Admin session preservation, explicit Google connections, invitation consumption/cohort assignment, persistent links on repeat login, unverified/different-owner rejection, and anonymous invitation signup. The cause was allauth logging out an already authenticated account before signup, clearing its pending invitation. No live account data was edited to work around the issue, and no schema migration was needed for this fix.

- 43 Django tests passed with `unbound.test_settings`, synthetic SQLite data, and mocked/no external services. Includes task permissions and shared progress, availability grids and all-busy submissions, per-user Google mirrors, Admin page rendering, signup/invitation checks, idempotent reminder batches, and a migration upgrade preserving a custom phase and an existing completed poll response.
- 10 Node tests passed against the frontend helpers used by the dashboard, including hostile-text rendering, permissions, URLs/style tokens and HTTP failure handling.
- Django regular system check: no issues. Model/migration consistency: no changes detected.
- Production-mode static collection: 166 files copied and 474 post-processed successfully.
- Production configuration check: only W005/W021 for HSTS include-subdomains/preloading. Those defaults await a domain/TLS policy decision. No warnings were silenced.
- JavaScript syntax and Git whitespace checks passed.

Not verified here: actual PostgreSQL connectivity/behavior, Azure startup/network configuration, live Google APIs and OAuth, real inbox delivery, interactive browser acceptance, or upgrading the divergent old local database. These require staging configuration and authorized accounts/data. No deployment or real message sending occurred. The original local checkout/database remain preserved.
