# Running UNbound

Sign in at `/admin/` to open the **Coordinator workspace**. Its shortcuts depend on your staff permissions.

| From the Admin home page | What you can do |
| --- | --- |
| **Assignments** | Choose **Assign work** to create a task or **Manage assignments and email drafts** to open the task list. **Overdue assignments** opens the same list filtered to overdue work. |
| **Scheduling** | Choose **Open a WhenBound poll** to collect availability or **Publish a confirmed meeting** once the time is set. **Active WhenBound polls** lists the open polls. |
| **Fellows and cohorts** | Open **Fellows and awards** to update a fellow or award a badge, **Cohort projects and phases** to update a cohort, or **Generate invitations** for five single-use codes. |
| **Resources** | Choose **Publish a resource** to share a link, **Manage resources** to edit its audience or publication status, or **Manage cohort resources and pins** to open a cohort. |

Expand **Program setup and all records** to reach the individual lists, including **Badges**, **Phases**, and **Invite codes**.

## Task email drafts

1. Open **Admin → Tasks**. To narrow the list, search by task or fellow, or filter by cohort, scope, source, status, or deadline.
2. Leave all rows unchecked and click **Email about overdue tasks** to include overdue, incomplete tasks matching the list. To choose specific work, check the task rows. The same button changes to **Email about selected tasks** and includes selected incomplete work, even if its deadline is in the future or blank.
3. Expand a draft to review its **To**, **Subject**, and **Message**. Personal tasks are grouped into one draft per fellow. Shared team tasks are grouped into one draft per cohort, with eligible members together in **To**, so those recipients can see each other's addresses. Drafts use active fellows’ verified Google sign-in addresses. The preview reports fellows skipped for a missing verified address.
4. Edit the subject or message, choose **Open in mail app**, then send from your mail app. For webmail or long drafts, copy the **To** and **Subject** fields and use **Copy message** for the body. You can also select and copy the text directly.

If the email button is missing from **Tasks**, the coordinator needs permission to view or change tasks and to change fellows.

## Badges and fellowship ranks

To award a milestone, open **Fellows and awards**, click the fellow’s name, mark the badge **Earned** in their badge rows, and click **Save**. To change the milestone itself, open **Badges** and edit its name, artwork, earning rule, or XP reward. Coordinators can choose one of the 15 supplied illustrations or upload a custom image.

Mission Control and Milestones show the fellow’s rank from their earned badge count. Their cohort’s **Current phase** is managed under **Cohort projects and phases**.

| Earned badges | Fellowship rank |
| --- | --- |
| 0 | Pioneer • Level 1 |
| 1–3 | Explorer • Level 1 |
| 4–6 | Trailblazer • Level 2 |
| 7–8 | Visionary • Level 3 |
| 9 or more | UNbound Legend • Level 4 |

## Program records

The launch configuration uses Google for identity only. Fellows still use invitations, UNbound assignments, manual meeting availability, cohorts/phases, badges and personalization. Drive browsing/shared-file discovery, Calendar events/conflict highlighting/import, and Google Tasks mirrors are deferred. Staff can share ordinary Drive or Calendar links separately using Google’s sharing permissions. No Google Workspace subscription is required for this sign-in mode. See [LAUNCH.md](LAUNCH.md) for deployment and re-enabling details.

- **Cohort resources.** In Django Admin, open **Cohorts**, select a cohort and add a resource under **Cohort resources and pins**. Paste the HTTPS link and preview the card. Fellows see the link under **Resources**. Grant file or folder access in Drive, with Viewer for reading or Editor for contributing.
- **Cohort pins.** Fellows share files or folders in Drive, then paste the sharing link into **Resources → Cohort pins**. Fellows can unpin their own links. Coordinators manage pins in the cohort’s resources in Admin. The **Pinned by** field identifies pins from fellows.
- **Shared resources.** Publish a link from **Admin → Shared resources**. Choose **All cohorts** to include future cohorts or **Selected cohorts** to choose the audience. Display type defaults to the URL’s detected type and the icon defaults to the displayed type. Choose either field manually and check the **Fellow dashboard preview** before publishing. Clear **Is published** to remove the card from dashboards.
- **Confirmed meetings.** Add an event under **Admin → Confirmed meetings** with a cohort, start and end in Monterrey time, and an optional Google Meet link. Fellows see the event in **Next Up** and **Meeting Hub**, where they can download an `.ics` file. A downloaded event reflects the meeting at the time of export.
- **Fellows:** connect a user to a cohort/chapter and choose the fellowship role. Fellowship role does not grant staff access. Administrators grant Staff status and the UNbound coordinators group under Users. Token fields are excluded from the operator form.
- **Cohorts:** maintain dates, project details, goals, and select the current phase. Manage phase names, descriptions and order under Phases; the student roadmap uses the same catalog. Referenced phases cannot be deleted.
- **Assignments:** Add opens the guided assignment form. Select a person, a cohort, or everyone, then choose individual or shared-team work. A team task is one shared completion; an individual task must be completed by each fellow. Completed records stay in the assignments list; filter by status to find them.
- **Task deadlines:** fellows enter dates and optional times in Monterrey time. The browser supplies the calendar and clock popups, so their appearance varies across browsers and operating systems.
- **WhenBound Requests.** Choose a cohort or all fellows. In **Possible meeting times**, use the date picker and **Add date** for each specific day, or leave **Specific dates** blank and enter a continuous range. The earliest and latest dates can span up to 42 days inclusive. Set the hours in Monterrey time. The end hour is exclusive and 24 means midnight. Set **Respond by** for the linked task. An active poll accepts late responses and an all-busy response counts as submitted. Changing the dates or hours after fellows respond requires confirmation to clear their responses and request them again.
- **Reminder delivery records:** operators can inspect the status of existing batches under **Reminder deliveries**. Review any interrupted `sending` record before attempting a retry.
- **Invitations:** choose an explicit cohort and role. A blank cohort leaves a new fellow unassigned. The default code is single-use. Existing Google login is unchanged.

### Independent staff and fellow sign-in

Staff sign into `/admin/` with their staff username and password. Fellows sign into `/dashboard/` with Google, using an invitation only to enroll initially. Each fellow has an internal user record; this never grants Admin access. Admin and portal use separate sessions and separate session-backed CSRF secrets, so different people can be signed into the two areas in the same browser. Logging out of one area keeps the other signed in.

Admin login never creates a Fellow profile or links a Google identity. A staff member can also be a fellow if explicitly enrolled; staff permissions are assigned separately. Google identities are never automatically attached to existing local accounts merely because emails match. Explicit linking is available only to an authenticated portal account, using verified Google credentials and an invitation when enrollment is incomplete.

After upgrading to the isolated sessions, reopen both login pages once. Old shared cookies are ignored. This does not delete accounts, identity links, assignments, or invitations. A form opened before the upgrade may need reloading. CSRF protection remains enforced; an expired form provides a safe recovery page.

Setup administrator: run `python manage.py setup_staff_group` after migrations. The command creates permissions but grants no users access. Only a trusted administrator should assign that group and Staff status.
