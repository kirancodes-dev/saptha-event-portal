# Multi-tenancy: what exists and what does not

**SapthaEvent runs one institution per deployment.** Each institution gets its
own service, database, storage bucket and secrets. That separation, not
anything in the application, is what keeps one institution's data away from
another's. To add an institution, repeat
[INSTITUTION_SETUP.md](INSTITUTION_SETUP.md).

An earlier version of this page described several institutions sharing one
deployment with "complete data isolation". That was never true of the code,
and this page replaces it.

## What the code has

| Piece | What it does | What it does not do |
|---|---|---|
| `middleware_tenant.py` | On non-public pages, looks up an organisation record from the subdomain, an `/org/<slug>/` path, an `X-Tenant-Domain` header, a token's `org_id` or the session, and puts it in `g.org` (templates see it as `org`). | It restricts nothing. No query filters by `g.org`, and no permission check reads it. |
| `organization_id` columns | Present on core records; every record is written with `default`. | They are not used to separate data. |
| `routes_onboarding.py` | A sign-up form that creates an organisation record and a `TenantAdmin` account. | It answers 404 unless `MULTI_TENANT_ENABLED=true`. It is off in production and must stay off: turning it on would let a stranger create an account in the one shared database. |
| `services_control_plane.py` | Plan and quota bookkeeping for organisation records. | Nothing in the running app enforces those quotas. |

So a request that names another organisation (a header, a path, a subdomain)
changes at most which organisation record a template can read. It gives no
access to anything: access is decided by the signed-in account's role and by
ownership of the event or unit (`services_permission.can`).

## What actually separates people's data inside a deployment

- Roles and ownership: an organiser sees and changes only events they host or
  are assigned to; department and unit admins only their unit's; Super Admins
  everything. Tests: `tests/test_scoped_roles_e2e.py`, `tests/test_exports.py`,
  `tests/test_institution_setup.py`.
- A person's own data export contains only their own records
  (`tests/test_privacy_rights.py`).

## If shared multi-tenancy is ever wanted

It is a project of its own, not a switch: every query needs an organisation
filter, every permission check an organisation boundary, uploads and
certificates need per-organisation storage paths, sessions and sign-in need to
be bound to an organisation, and each of those needs tests that try to cross
the boundary. Until that is built and verified, do not set
`MULTI_TENANT_ENABLED`, and do not describe the product as multi-tenant.
