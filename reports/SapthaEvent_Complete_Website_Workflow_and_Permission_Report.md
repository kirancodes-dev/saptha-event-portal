![Sapthagiri NPS University Logo](../static/snpsu-logo.png)

<style>
table { table-layout: fixed; width: 100%; word-break: break-word; white-space: normal; border-collapse: collapse; }
th, td { padding: 6px 8px; vertical-align: top; }
thead th { background: #1a2557; color: #fff; }
tbody tr { background: #fff; }
.signature-table td { min-width: 120px; }
</style>

# SapthaEvent Portal
## Complete Website Workflow and Permission Approval Report

**Institution:** Sapthagiri NPS University

**Department:** Computer Science & Engineering

**Project:** SapthaEvent Enterprise Event Management Portal

**Report Type:** Workflow, Permission, and Approval Documentation

**Report Date:** 08 June 2026

**Prepared by:** SapthaEvent Development Team

---

\newpage

## Page 1 — Cover Page

This report documents the complete website workflow for the SapthaEvent Portal, including the technology architecture, user journeys, permission and approval processes, stakeholder responsibilities, deployment approach, compliance requirements, and the final approval checklist.

The report is organized in a standard academic and professional format with an executive summary, detailed workflow chapters, permissions and approvals, and a final sign-off section.

---

\newpage

## Page 2 — Document Control

- Document Owner: SapthaEvent Development Team
- Approval Authority: Head of Department, CSE
- Version: 1.0
- Status: Draft for submission
- Distribution: College authorities, department administrator, project guide, and technical committee

### Document Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0 | 08 Jun 2026 | Development Team | Initial full workflow and permission report |

---

\newpage

## Page 3 — Table of Contents

1. Executive Summary
2. Introduction
3. Scope and Objectives
4. Stakeholder Matrix
5. Project Context
6. System Features Overview
7. Architecture Overview
8. Technology Stack
9. User Role Model
10. Super Admin Workflow
11. Admin Workflow
12. Club SPOC Workflow
13. Judge Workflow
14. Coordinator Workflow
15. Participant Workflow
16. Event Creation Process
17. Registration Process
18. Payment and Coupon Process
19. Live Event and Leaderboard Process
20. Certificate and Verification Process
21. Reporting and Analytics Process
22. Data Model Overview
23. Security and Access Control
24. Authentication and Authorization
25. Permission Request Approach
26. Approval Workflow and Gatekeepers
27. Compliance and Data Privacy
28. Deployment and Release Workflow
29. Testing and Quality Assurance
30. Operational Readiness
31. Risk Assessment
32. Maintenance and Support
33. Training and Handover
34. Future Enhancements
35. Conclusion and Approval Checklist

---

\newpage

## Page 4 — Executive Summary

This report presents the complete website workflow for SapthaEvent, a multi-tenant enterprise event management portal built for Sapthagiri NPS University.

The website supports all stages of event planning, execution, and reporting. It includes role-based access, secure authentication, online registration, payments, real-time live scoreboards, certificate generation, sponsor management, attendance scanning, and analytics.

The permission approach is designed to meet institutional approval needs by defining clear sign-off steps, stakeholder responsibilities, data handling permissions, and documented technical checkpoints.

---

\newpage

## Page 5 — Introduction

SapthaEvent is an integrated event orchestration platform tailored for academic institutions. The portal replaces manual event management with a digital system that supports multiple colleges, departments, clubs, and event categories.

This report explains how the portal works from the ground up, with a focus on the website workflow and the request-for-permission process necessary for official deployment and adoption.

---

\newpage

## Page 6 — Scope and Objectives

### Scope

- Full website workflow for SapthaEvent Portal
- All major user journeys and feature flows
- Authentication and permissions strategy
- Approval and permission request design
- Deployment and compliance requirements

### Objectives

- Document the complete website workflow for submission
- Present a structured permission and approval approach
- Demonstrate the portal’s readiness for institutional use
- Provide a reference document for technical and administrative review

---

\newpage

## Page 7 — Stakeholder Matrix

| Stakeholder | Role | Responsibility |
|---|---|---|
| Project Guide | Technical Advisor | Review workflow, verify architecture, recommend improvements |
| HOD, CSE | Approval Authority | Authorize deployment, sign permission form |
| College IT | Infrastructure Owner | Approve hosting environment, network access, security controls |
| Department Admin | Operations Lead | Coordinate pilot events and training |
| Club SPOC | Event Manager | Use portal to schedule events and manage participants |
| Judges | Evaluators | Score event participants via restricted dashboard |
| Coordinators | Logistics | Manage check-ins, access control, and live lists |
| Participants | End users | Register, attend, and verify certificates |

---

\newpage

## Page 8 — Project Context

The SapthaEvent portal is built in response to the need for a robust event management system at Sapthagiri NPS University. It is designed to handle event operations from registration through scoring and certification.

The platform is intended for use across technical clubs, cultural committees, sports events, institutional festivals, and inter-collegiate programs.

---

\newpage

## Page 9 — System Features Overview

The website includes the following major capabilities:

- Multi-tenant support for colleges and clubs
- Role-based dashboards for Super Admin, Admin, SPOC, Judge, Coordinator, Participant
- Event creation and management
- Online registration with team and solo modes
- Payment gateway integration and coupon handling
- Venue and room management
- Live leaderboard and projector-ready displays
- Attendance scanning via QR codes
- Certificate generation and verification
- Sponsor management
- AI-supported reporting and analytics
- Audit logging and logs review

---

\newpage

## Page 10 — Architecture Overview

SapthaEvent uses a layered architecture that separates presentation, application logic, and data storage.

Key architecture elements:

- Flask backend for business logic and API endpoints
- Firestore as the primary data store for events, registrations, users, and logs
- Template-driven UI for admin and participant flows
- Server-Sent Events (SSE) for real-time live dashboards
- Email delivery and scheduling using a priority-based provider chain
- PDF generation for certificates and reports
- External payment integrations for Razorpay and Stripe

---

\newpage

## Page 11 — Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python, Flask | Web framework and API layer |
| Database | Firestore / Firebase | Event data, user data, analytics |
| Frontend | HTML, CSS, JavaScript | Responsive dashboards and forms |
| Authentication | JWT, OAuth, 2FA | User sign-on and permission control |
| Email | BREVO / Resend / SMTP | Notifications and transactional email |
| Payments | Razorpay, Stripe | Online payments and refunds |
| Reporting | ReportLab, HTML print | PDF certificates and event reports |
| Hosting | Railway / cloud | Deployment platform |

---

\newpage

## Page 12 — User Role Model

The website implements a strong role model with least privilege access.

Roles:

- Super Admin
- Admin
- Club SPOC
- Judge
- Coordinator
- Participant

Each role has access to only the capabilities required for their responsibilities.

---

\newpage

## Page 13 — Super Admin Workflow

Super Admins perform the highest-level operations, including:

- Platform configuration and institution onboarding
- College and department registration
- Admin user assignment
- Access to all analytics and audit logs
- Approval and review of policy compliance

The workflow begins at login, proceeds through dashboard review, and ends with final permission issuance for the event platform.

---

\newpage

## Page 14 — Admin Workflow

Admins manage college-level operations.

Typical workflow:

1. Login to admin dashboard
2. Review event calendar and pending registrations
3. Create clubs and allocate SPOCs
4. Assign judges and coordinators
5. Review financial summary and payment reconciliations
6. Oversee compliance and permissions for each event

---

\newpage

## Page 15 — Club SPOC Workflow

Club SPOCs are event owners.

Their workflow includes:

- Creating new events with venue, date, and eligibility criteria
- Defining registration form schema and team rules
- Managing participant approvals
- Sending notifications and reminders
- Generating AI-powered event reports
- Reviewing live leaderboard performance

---

\newpage

## Page 16 — Judge Workflow

Judges access only score submission pages.

Workflow:

- Login to judge dashboard
- View assigned event rounds
- Open the scoring form for a team or individual
- Submit scores, comments, and feedback
- Verify responses before final submission

---

\newpage

## Page 17 — Coordinator Workflow

Coordinators handle logistics and attendance.

Workflow:

- Login and locate assigned events
- Scan participant QR codes at check-in
- Manage walk-ins and late registrations
- Activate attendance counters
- Trigger room assignment notifications

---

\newpage

## Page 18 — Participant Workflow

Participants consume the portal as event attendees.

Workflow:

- Discover live events and register
- Complete payment or apply coupons
- Download QR ticket and event details
- Attend event with QR check-in
- View certificate and results after evaluation

---

\newpage

## Page 19 — Event Creation Process

The event creation workflow is a structured multi-step process.

Steps:

1. Event metadata capture (title, category, date, venue)
2. Team and participant limits
3. Fees and payment rules
4. Prize structure and round layout
5. Judge assignment and scoring methods
6. Publish event to registration portal

A well-defined form walk-through ensures no required field is missed.

---

\newpage

## Page 20 — Registration Process

The registration workflow is optimized for both solo and team entries.

Key stages:

- User account creation or login
- Event selection and eligibility check
- Team member addition or individual registration
- Coupon code validation
- Payment confirmation
- Ticket generation and email delivery

The system also supports manual registration approval and payment verification by admins.

---

\newpage

## Page 21 — Payment and Coupon Process

Payment workflow supports secure online transactions.

Major steps:

- User selects payment provider
- Payment request created and redirected securely
- Payment webhook verifies transaction status
- Receipt email sent automatically
- Coupon discount and early-bird pricing handled in real time

All payments are logged and reconciled against event records.

---

\newpage

## Page 22 — Live Event and Leaderboard Process

Live workflow powers event-day operations.

Components:

- SSE channel for scoreboard updates
- Judge score feed into live ranking engine
- Podium display logic for top performers
- Real-time score adjustments and tie-breaking
- Live event status indicator visible to audience displays

This workflow ensures transparency and instant feedback.

---

\newpage

## Page 23 — Certificate and Verification Process

Certificate workflow creates and verifies achievement documents.

Process:

- Final results are published
- Certificate metadata is assembled
- PDF document is generated with university branding
- Unique cryptographic hash is stored
- Verification URL is issued to participants
- Public certificate validation page displays status and authenticity

---

\newpage

## Page 24 — Reporting and Analytics Process

Reporting is available to admins and SPOCs.

It includes:

- Participant counts and event attendance
- Revenue and fee analysis
- Judge performance and event scores
- Sponsor visibility and support contribution
- Post-event AI recommendations and summary

Reports are exportable and print-ready.

---

\newpage

## Page 25 — Data Model Overview

The website stores structured data for the following entities:

- Users (roles, authentication, profile)
- Colleges and departments
- Clubs and club assignments
- Events and event rounds
- Registrations and teams
- Payments and coupons
- Attendance and QR scans
- Certificates and verification hashes
- Audit logs and activity trails
- Reports and analytics summaries

The data model is designed for horizontal scalability.

---

\newpage

## Page 26 — Security and Access Control

The platform secures data with role-based access and authorization checks.

Security controls include:

- Per-route access validation
- Session and token verification
- Audit logging for sensitive operations
- Admin lockout and account recovery
- HTTP security headers and content policies
- Secure file access for certificates and reports

---

\newpage

## Page 27 — Authentication and Authorization

Authentication uses multiple mechanisms.

Supported flows:

- Username/password login
- JWT bearer tokens for APIs
- OAuth single sign-on if configured
- Two-factor authentication for privileged roles

Authorization is enforced by checking role membership and resource ownership before any action.

---

\newpage

## Page 28 — Permission Request Approach

The permission approach is the central topic of this report.

This section defines how approvals are requested, tracked, and granted for the website.

The approach is based on three steps:

1. **Technical Approval**: Review by the development guide and college IT team
2. **Operational Approval**: Review by department administration and event coordinators
3. **Formal Permission**: Final sign-off by the Head of Department or Dean

Each step is documented with sign-off forms, review checklists, and handover notes.

---

\newpage

## Page 29 — Approval Workflow and Gatekeepers

### Gatekeepers

- IT Infrastructure Team: approves hosting environment and network access
- Data Privacy Officer: approves data-handling design and consent flow
- Event Committee Chair: approves event schedules and permissions
- HOD / Principal: final platform approval for institutional use

### Approval flow

1. Submit project brief to guide and HOD
2. Share architecture and security plan
3. Review with IT and compliance team
4. Adjust implementation based on feedback
5. Seek final sign-off and publication permission

The workflow is repeated for major releases and new event deployment cycles.

---

\newpage

## Page 30 — Compliance and Data Privacy

The portal is designed with data privacy in mind.

Compliance items:

- Personal data is encrypted in transit
- Consent required before registration
- Right to update or delete personal data
- Audit trail for all sensitive actions
- Role-based restrictions on who can view participant data
- Secure handling of payment records and receipts

This meets institutional policies and modern privacy expectations.

---

\newpage

## Page 31 — Deployment and Release Workflow

Deployment workflow covers the transition from development to production.

Steps:

- Code review and test validation
- Environment configuration for production
- Database and Firestore collection readiness
- Secure deployment to Railway or chosen cloud provider
- Smoke testing after release
- Final permission notice to the operations team

A staging environment is also recommended for pre-release validation.

---

\newpage

## Page 32 — Testing and Quality Assurance

The platform has been validated through a structured QA process.

Testing includes:

- Unit tests for backend logic
- Integration tests for API endpoints
- Manual walkthroughs for each role
- Live scenario simulations with event creation and registration
- Payment gateway validation
- Certificate generation and verification checks
- Access control and permission tests

Test results are documented and stored with each release.

---

\newpage

## Page 33 — Operational Readiness

Operational readiness confirms the platform is ready for actual event use.

Readiness checklist:

- All key user roles verified
- Event workflow completed end-to-end
- Live scoreboard tested on projectors
- Email notifications and reminders sent correctly
- Payment processing validated
- Certificate and verification page confirmed
- Auditing and logs verified

Once ready, the system is eligible for a pilot rollout.

---

\newpage

## Page 34 — Risk Assessment

Identify and manage the most important risks.

Primary risks:

- Data privacy gaps from incorrect access settings
- Payment transaction failure or duplication
- Live scoreboard latency during peak usage
- Incorrect judge scoring entry
- Event schedule drift and room conflicts
- Insufficient training for coordinators and judges

Risk mitigation:

- Apply strict permission checks
- Use reliable payment providers with webhook verification
- Test SSE performance on target hardware
- Build judge entry validation and confirmation flows
- Use event calendar conflict checks
- Conduct training sessions before live events

---

\newpage

## Page 35 — Maintenance, Support, and Future Enhancements

This report also covers long-term support and future improvements.

Maintenance plan:

- Weekly backup of Firestore data
- Monthly review of audit logs
- Quarterly security review and patching
- Regular user feedback collection
- Continuous improvement of event workflows

Future enhancements:

- Mobile app support for participants
- Additional payment providers for global events
- AI-based event recommendation engine
- Enhanced reporting dashboards
- Student achievement portfolio and analytics

---

\newpage

## Final Approval Checklist

- [ ] Project brief submitted to HOD and guides
- [ ] Technical architecture reviewed
- [ ] Security and access controls documented
- [ ] Compliance and privacy requirements confirmed
- [ ] Deployment and staging workflow established
- [ ] User roles and workflows tested
- [ ] Permission request process defined
- [ ] Final sign-off form prepared
- [ ] Platform ready for pilot event deployment

---

\newpage

### Signatures

<div class="signature-table">
<table>
	<thead>
		<tr><th>Stakeholder</th><th>Name</th><th>Signature</th><th>Date</th></tr>
	</thead>
	<tbody>
		<tr><td>Project Guide</td><td></td><td></td><td></td></tr>
		<tr><td>Head of Department</td><td></td><td></td><td></td></tr>
		<tr><td>IT Infrastructure Lead</td><td></td><td></td><td></td></tr>
		<tr><td>Event Committee Chair</td><td></td><td></td><td></td></tr>
	</tbody>
	</table>
</div>
---

**Note:** This report is prepared as the formal documentation of the SapthaEvent Portal website workflow and permission approach. It is designed to support submission and approval by institutional authorities.
