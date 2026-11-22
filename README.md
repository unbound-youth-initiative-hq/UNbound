# UNbound delivery branch

The Django application is in `backend/`. The Render release branch is `basic-launch`.

- [Setup and deployment](docs/DEPLOYMENT.md)
- [Staff operator guide](docs/OPERATIONS.md)

For local use, activate `backend/.venv`, copy `backend/.env.example` to `backend/.env`, supply your Google OAuth credentials, and run the commands in the setup guide. This fresh checkout has no copied database or secrets.

From `backend/`, run:

```sh
python manage.py test fellows --settings=unbound.test_settings
node --test tests/dashboard-utils.test.cjs
```

This branch fixes assignment permissions and shared completion, unsafe frontend text rendering, availability validation/submission, demo-data side effects, reminder confirmation/queuing, and production settings. Django Admin now provides daily-work shortcuts and grouped forms, with an editable phase catalog and cohort dropdown.

Coordinators manage badge artwork under **Badges**, award milestones under **Fellows**, and prepare individual or cohort email drafts under **Tasks**. The coordinator reviews and sends each draft from their mail app. [Coordinator workspace guide](docs/OPERATIONS.md)
