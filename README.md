# UNbound delivery branch

This Django application is in `backend/`. Active branch: `codex/delivery-readiness`, based on `testing/backend` at f597e5b.

- [Setup and deployment](docs/DEPLOYMENT.md)
- [Staff operator guide](docs/OPERATIONS.md)

For local use, activate `backend/.venv`, copy `backend/.env.example` to `backend/.env`, supply your Google OAuth credentials, and run the commands in the setup guide. This fresh checkout has no copied database or secrets.

From `backend/`, run:

```sh
python manage.py test fellows --settings=unbound.test_settings
node --test tests/dashboard-utils.test.cjs
```

This branch fixes assignment permissions and shared completion, unsafe frontend text rendering, availability validation/submission, demo-data side effects, reminder confirmation/queuing, and production settings. Django Admin now provides daily-work shortcuts and grouped forms, with an editable phase catalog and cohort dropdown.

Azure provisioning, live Google verification, migration of the divergent local database, and real email activation remain environment-specific release steps. Coordinators can upload badge artwork and prepare individual assignment drafts for selected fellows in Django Admin.
