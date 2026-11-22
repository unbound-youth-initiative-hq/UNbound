# Running UNbound

Sign in at `/admin/`. The home page has shortcuts for daily work.

The launch configuration uses Google for identity only. Fellows still use invitations, UNbound assignments, manual meeting availability, cohorts/phases, badges and personalization. Drive browsing/shared-file discovery, Calendar events/conflict highlighting/import, and Google Tasks mirrors are deferred. Staff can share ordinary Drive or Calendar links separately using Google’s sharing permissions. No Google Workspace subscription is required for this sign-in mode. See [LAUNCH.md](LAUNCH.md) for deployment and re-enabling details.

- **Cohort resources.** In Django Admin, open **Cohorts**, select a cohort and add a resource under **Cohort resources and pins**. Paste the HTTPS link and preview the card. Fellows see the link under **Resources**. Grant file or folder access in Drive, with Viewer for reading or Editor for contributing.
- **Cohort pins.** Fellows share files or folders in Drive, then paste the sharing link into **Resources → Cohort pins**. Fellows can unpin their own links. Coordinators manage pins in the cohort’s resources in Admin. The **Pinned by** field identifies pins from fellows.
- **Shared resources.** Publish a link from **Admin → Shared resources**. Choose **All cohorts** to include future cohorts or **Selected cohorts** to choose the audience. Display type defaults to the URL’s detected type and the icon defaults to the displayed type. Choose either field manually and check the **Fellow dashboard preview** before publishing. Clear **Is published** to remove the card from dashboards.
- **Confirmed meetings.** Add an event under **Admin → Confirmed meetings** with a cohort, start and end in Monterrey time, and an optional Google Meet link. Fellows see the event in **Next Up** and **Meeting Hub**, where they can download an `.ics` file. A downloaded event reflects the meeting at the time of export.
- **Fellows:** connect a user to a cohort/chapter and choose the fellowship role. Fellowship role does not grant staff access. Administrators grant Staff status and the UNbound coordinators group under Users. Token fields are excluded from the operator form.
- **Cohorts:** maintain dates, project details, goals, and select the current phase. Manage phase names, descriptions and order under Phases; the student roadmap uses the same catalog. Referenced phases cannot be deleted.
- **Assignments:** Add opens the guided assignment form. Select a person, a cohort, or everyone, then choose individual or shared-team work. A team task is one shared completion; an individual task must be completed by each fellow. Completed records stay in the assignments list; filter by status to find them.
- **Task deadlines:** fellows enter dates and optional times in Monterrey time. The browser supplies the calendar and clock popups, so their appearance varies across browsers and operating systems.
- **Meeting requests:** choose a cohort or all fellows and a date/hour window (maximum 42 days). The ending hour is exclusive; 24 means midnight. All-busy responses count as submitted. Changing dates or hours clears old responses and requests resubmission. Updating instructions/deadline updates linked tasks.
- **Task email drafts:** in **Admin → Tasks**, click **Email about overdue tasks** to draft reminders for overdue work matching the current filters. Checking tasks changes the button to **Email about selected tasks** and includes the selected incomplete tasks. Personal tasks go into one draft per fellow and team tasks go into one draft per cohort, addressed to active fellows with verified Google email addresses. Review and edit the drafts before opening them in your mail app.
- **Reminder delivery records:** operators can inspect the status of existing batches under **Reminder deliveries**. Review any interrupted `sending` record before attempting a retry.
- **Badges:** names/descriptions and earning rules are editable. Manual awards are on the Fellow's badge rows. Choose one of the 15 supplied illustrations or upload a custom image on the badge form.
- **Invitations:** choose an explicit cohort and role. A blank cohort leaves a new fellow unassigned. The default code is single-use. Existing Google login is unchanged.

### Independent staff and fellow sign-in

Staff sign into `/admin/` with their staff username and password. Fellows sign into `/dashboard/` with Google, using an invitation only to enroll initially. Each fellow has an internal user record; this never grants Admin access. Admin and portal use separate sessions and separate session-backed CSRF secrets, so different people can be signed into the two areas in the same browser. Logging out of one area keeps the other signed in.

Admin login never creates a Fellow profile or links a Google identity. A staff member can also be a fellow if explicitly enrolled; staff permissions are assigned separately. Google identities are never automatically attached to existing local accounts merely because emails match. Explicit linking is available only to an authenticated portal account, using verified Google credentials and an invitation when enrollment is incomplete.

After upgrading to the isolated sessions, reopen both login pages once. Old shared cookies are ignored. This does not delete accounts, identity links, assignments, or invitations. A form opened before the upgrade may need reloading. CSRF protection remains enforced; an expired form provides a safe recovery page.

Setup administrator: run `python manage.py setup_staff_group` after migrations. The command creates permissions but grants no users access. Only a trusted administrator should assign that group and Staff status.
