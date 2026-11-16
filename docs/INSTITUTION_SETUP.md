# Setting SapthaEvent up for an institution

Who this is for: the person who deploys SapthaEvent for a university or
college, and the institution's first administrator.

**One deployment serves one institution.** There is one database and one set
of accounts; pages do not filter by organisation. A second institution gets
its own deployment (its own service, database, storage bucket and secrets),
set up by repeating this document. See [MULTI_TENANCY.md](MULTI_TENANCY.md) for
why, and for what the older "tenant" code does and does not do.

Nothing here creates an institution by public sign-up. Every step is done by
whoever holds the deployment's credentials, or by a signed-in Super Admin.

## 1. Deploy

Follow [DEPLOY.md](DEPLOY.md): the service, the database and its migrations,
the storage bucket, the mail provider, the scheduler, and the first Super
Admin account ("First Super Admin"). Set `BASE_URL` to the address people will
open; links in emails are built from it.

### A demo copy or the institution's own deployment

A copy of the portal that exists to be shown, with sample data, is marked with
`DEMO_ENVIRONMENT=1` in its settings. It then says "Demo" at the top of every
page (not on scanners, kiosks and printed pages), and the public About page
(`/about`) says "You are on a demo now". The setting changes nothing else.

An institution's own deployment never sets it. With `FLASK_ENV=production` and
no `DEMO_ENVIRONMENT`, the About page says the portal is the institution's own
and that registrations made there are real. Do not load demo data
(`seed.py`, `demo_reset.py`) into an institution's deployment; both refuse a
production-looking database.

The About page is the public description of the portal for someone deciding
whether to use it: who it is for, what it covers and does not do, how an
institution starts, what a demo can and cannot show, and the support address
from the setup page. It states no price, customer or certification.

## 2. Institution setup page

Sign in as the Super Admin and open **More → Institution setup**
(`/admin/institution`). Only Super Admins can open it.

| Field | Used for | Rule |
|---|---|---|
| Name | Page footer, new certificates | 2–120 characters |
| Short name | Kept with the details | up to 20 characters, optional |
| Public address | The readiness check compares it with the address in use | `https://host`, nothing after it (`http://` only for localhost) |
| Support email | Help and privacy pages | a valid address, optional |
| Certificate main / accent colour | New certificates | `#` and six hex digits |

A wrong value is refused with the reason next to the field, and nothing is
saved. Every save writes an audit entry (`INSTITUTION_DETAILS_SAVED`) naming
who changed which fields; see **Audit log**.

Saved values override these environment defaults: `COLLEGE_NAME`,
`SUPPORT_EMAIL`, `CERT_PRIMARY_COLOR`, `CERT_ACCENT_COLOR`.

### What the page does not change

These still need a code or environment change for an institution other than
Sapthagiri NPS University, and a redeploy:

- The home page's facts about the university (address, phones, schools, social
  accounts, campus photos): `university_info.py`.
- The institution's name where a template writes it out (page titles, the home
  page, email templates). Search the `templates/` folder for the name.
- The logo: the file named by `COLLEGE_LOGO_PATH` (default
  `static/img/email-logo.png`), and the app icons in `static/`.
- `BASE_URL`, the mail sender (`MAIL_FROM`) and every secret: the server's
  environment, never this page.

## 3. First administrators

On the same page, under **Administrators**, enter the name and email of the
institution's own administrator and choose **Invite**. This uses the normal
"add a user" flow: the account is created locked, and the person gets an
emailed link to choose their own password. Nobody else ever knows it. Until
they use the link the page lists them as "Invited", and the link can be
resent from their user page.

Have at least two administrators who can sign in, so nobody is locked out
when one person leaves. Email must be configured for the invitation to arrive
(the readiness list says whether it is).

Other roles are added under **Users** (SPOCs, coordinators, judges,
department admins) and **Units & roles** (schools, departments, clubs and the
people who run them).

## 4. Readiness list

The right-hand list is read from the deployment each time the page opens;
nothing is ticked by hand:

| Item | Done when |
|---|---|
| Details saved | the form above has been saved at least once |
| Public address | it is saved, starts with `https://`, and is the address the page was opened at |
| Two administrators | two Super Admin accounts have set a password |
| Help address | a support email is in force |
| Units | at least one school, department or club exists |
| Email | a mail provider is configured |
| Uploads | file storage is a bucket (`STORAGE_TYPE` is `gcs` or `s3`), not the server's disk |
| Scheduled jobs | `CRON_SECRET` is set (the scheduler itself is set up in DEPLOY.md) |

The list shows yes or no, never a secret's value. **System status**
(`/admin/system`) has the full list of connected services.

## 5. Handover to the institution

1. The institution's administrators are invited and have signed in (step 3).
2. The deploying person's own Super Admin account is deactivated from its user
   page, or kept by written agreement. Deactivating ends its open sessions.
3. `SUPER_ADMIN_PASS` is removed from the service's settings (DEPLOY.md).
4. Secrets (database, mail, storage, session key, `CRON_SECRET`) are rotated
   if anyone who will no longer operate the deployment has seen them.
5. The institution confirms who receives the support address and who can
   reach the hosting account.
6. Run the release check in DEPLOY.md once from the institution's address.

## 6. Exporting the institution's data

- **Everything:** a database backup is a complete copy (`scripts/backup_db.sh`,
  DEPLOY.md "Backups"); `scripts/restore_db.sh` restores it into an empty
  database. Uploaded files and certificates are in the storage bucket and are
  copied with the cloud provider's own tools.
- **By event:** organisers download registrations, attendance, results,
  feedback and certificates as CSV or Excel from the event's pages; Super
  Admins download cross-event summaries from **Analytics**, **A4 report** and
  the event review. See the reports section of the organiser pages.
- **One person:** each person downloads their own data from their profile
  (see [DATA_HANDLING.md](DATA_HANDLING.md)).

A backup holds every person's records. Keep it in a private bucket, and never
in the repository.

## 7. Closing a deployment down (offboarding)

Done by whoever holds the hosting account, on the institution's written
instruction:

1. Agree a date and tell users through the institution's own channels. The
   portal sends nothing on its own for this.
2. Close registration on open events; let running events finish.
3. Take a final backup and copy the storage bucket; hand both to the
   institution through a channel they choose. Confirm they can open them.
4. Stop the scheduler jobs, then the service.
5. Delete the database, the storage bucket, the backups and the secrets after
   the retention period the institution states in writing. Record the date.
6. Remove DNS records and sign-in (OAuth) client registrations for the
   address.

How long data must be kept before step 5, and who may instruct deletion, are
the institution's legal decisions; this document does not answer them.
