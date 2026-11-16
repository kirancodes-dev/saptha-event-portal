# Connecting SapthaEvent to campus systems

What the portal can exchange with other systems today, how to set each one
up, and what it cannot do. Nothing here needs a secret written into a file in
the repository: secrets are environment variables (Secret Manager on Cloud
Run, `docs/DEPLOY.md`).

## At a glance

| Need | How | Direction |
|---|---|---|
| Load the student roster | CSV upload, checked before it is applied | in |
| Give students their events in a calendar app | Personal subscription link (`.ics`) | out |
| Add one event to a calendar | `.ics` file from the event page | out |
| Take registrations, attendance and results into a spreadsheet | CSV and Excel downloads | out |
| Institution-wide reports | Admin and NAAC report downloads | out |
| Sign in with the institution's Google accounts | Google sign-in (optional) | in |
| Read or write from a program | REST API (`docs/API.md`) | both |

Not available: a connector for any particular ERP, LMS or student-information
system; outgoing webhooks; SAML; automatic roster sync. A campus system that
can export CSV can feed the roster; one that can import CSV or read an API can
take the portal's data.

## Student roster (CSV)

Super Admin → Users → "Import Student Roster (CSV)".

1. Upload a CSV file. The first row names the columns: `email` (required),
   `name`, `usn`, `department`, `year`, `section`, `cgpa`, `backlogs`. Order
   and capitals don't matter; common other headings are understood (`roll_no`,
   `dept`, `branch`, `student_name`, `email_id`, `gpa`). A sample file is on
   the page. Limits: 2 MB and 5,000 rows a file.
2. The portal shows a preview and changes nothing. For every row: a new
   student, an existing student with the fields that would change, already up
   to date, or not usable and why (no email, a malformed email, the same email
   or USN twice in the file, a USN that belongs to another account, a CGPA or
   backlog count that is not a number, an email that belongs to a staff
   account). The unusable rows can be downloaded to fix.
3. Choose what happens to students who already have an account: update them
   with the file's values (an empty cell changes nothing), or leave them and
   only add new students. Then confirm, or cancel.

Only the rows with nothing wrong are applied. The upload waits at most an hour
and only for the administrator who uploaded it; it is deleted on confirm,
cancel or expiry. The import is recorded in the audit log with its counts.

The import does not delete or deactivate students who are missing from the
file, and it does not email anyone. A new student uses "Forgot password" on
the login page to set a password.

A script can post the same file to `POST /admin/users/import_csv` as a signed-in
Super Admin: it applies the usable rows at once, with the same checks and no
preview.

## Calendars

- **A student's own events:** "Subscribe" on My Events and on the public
  calendar gives a private link ending in `/calendar/feed.ics?token=...`.
  Calendar apps (Google, Apple, Outlook) refresh it on their own schedule.
  The link shows only that person's registrations. "Reset link" makes every
  earlier link stop working.
- **One event:** the event page offers an `.ics` file.

There is no institution-wide calendar feed of all events, and the portal does
not write into a campus calendar.

## Downloads

| What | Where | Who |
|---|---|---|
| An event's registrations (CSV, Excel), including participant type and institution | The event's Registrations page | The event's organisers |
| The filtered registrations list with what to fix | Registrations page → Download | The event's organisers |
| Event summary for a range of event dates: registrations, attendance and no-shows, results, feedback and certificates for each event, with what each column counts (CSV; Excel with the definitions on a second sheet) | Analytics → Event summary report (`/reports/events`) | Super Admin (every event); organisers (their own events) |
| An event's feedback responses (CSV) | The event's feedback page | The event's organisers |
| An event's certificates (CSV, Excel) | The event's certificates page | The event's organisers |
| Certificates issued per department, event type and month (CSV) | `/certificates/reports/counts` | Super Admin |
| Department activity ledger (CSV; Excel with `?format=xlsx`) | `/admin/export/department_activity` | Super Admin |
| NAAC activity report (Excel, PDF) | NAAC report | IQAC coordinator, Super Admin |
| A person's own data (JSON) | Profile → Download my data | That person |

## Sign in with Google (optional)

Without it, people sign in with an email address and password; nothing else
needs setting up.

To switch it on:

1. In Google Cloud Console create an OAuth client (type: Web application).
   Authorised redirect URI: `<BASE_URL>/auth/google/callback`.
2. Set `OAUTH_GOOGLE_CLIENT_ID` and `OAUTH_GOOGLE_CLIENT_SECRET` on the
   service (the secret through Secret Manager).
3. To accept only the institution's accounts, set `UNIVERSITY_EMAIL_DOMAIN`
   to its domain (several, separated by commas).
4. `BASE_URL` must be the address people use, or Google refuses the redirect.

How to tell it is working: Admin → System lists "Google sign-in" as
configured, and the login page shows "Sign in with Google". Until both
variables are set the button is not shown.

What people see when it fails:

| Situation | Message |
|---|---|
| Not set up, and someone opens `/auth/google` directly | "Google login is not configured for this instance." |
| An account outside the allowed domain | "Google sign-in is restricted to university accounts (@domain)." |
| The person cancels at Google | "Google login cancelled: ..." |
| The sign-in was started in another tab or expired | "Invalid OAuth state. Please try again." |
| Google does not answer or refuses the code | "Google authentication failed. Please try again." |

In every case the person lands back on the login page and can still sign in
with a password.

Microsoft sign-in has routes in the code (`OAUTH_MICROSOFT_CLIENT_ID`,
`OAUTH_MICROSOFT_CLIENT_SECRET`) but the login page does not offer it and it
has not been verified. Treat it as not available.

## API

`docs/API.md` lists every endpoint. It is the API the mobile app uses: a
caller signs in as a user account. There are no API keys or service accounts,
so an integration needs an account of its own with the role it needs, and its
password stored as a secret on the calling side.

## Webhooks

The portal does not send webhooks. The only incoming webhook is the email
provider's delivery report.
