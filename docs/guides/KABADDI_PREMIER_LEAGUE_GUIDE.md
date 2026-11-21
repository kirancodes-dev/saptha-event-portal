# Running the Sapthagiri Kabaddi Premier League on the portal

This guide follows the Season-1 fixture sheet: 8 teams in two pools, home and
away in each pool, an inter-pool round, semi-finals across the pools, and a
final. That is 31 matches, M-01 to M-31. Do a demo run first (part 9), then
the real event.

## Who does what

| Person | What they do on the portal |
|---|---|
| **SPOC** (the event's owner) | Creates the event, assigns the coordinators, makes the fixtures (pools, seeds, home and away), adds team logos, uploads the schedule, makes the playoffs, publishes the results, issues the certificates. Can also score any match. |
| **Coordinator** (assigned to this event) | Scores matches live from a phone, or types in a final score. Checks teams in at the gate. Can't change the fixtures, the pools, the schedule or the logos. |
| **Teams and players** | Register (captain plus members) and get a ticket. Follow the fixtures, tables and live scores. |
| **Anyone** (audience, big screen) | Opens the public fixtures page and the live scoreboard. No login needed. |

Have one scorer for each match. Two people scoring the same match is safe,
because every tap is saved in order, but one scorer avoids confusion.

---

## 1. Create the event (SPOC)

1. SPOC console → **Create event**.
2. Type: **Sports tournament**. Sport: **Kabaddi**. Format: **League then knockout**.
3. Participation is **Team**, with 5 to 15 per team. For kabaddi use 7 players plus up to 5 substitutes.
4. Set the dates and the venue, then publish the event.

## 2. Get the 8 teams registered

- **Real event:** each captain registers the team on the event page with the
  team name and the members' names. The members' names fill the
  "Who scored" list during live scoring, which gives you top raiders and top
  defenders. The team is confirmed as soon as the captain registers; the
  members don't have to confirm anything and get no email. To ask members to
  confirm, use **Turn on** under "Team members' confirmation" on the
  registrations page.
- **Demo (fastest):** the coordinator adds each team as a walk-in
  (Coordinator → Scanner → **Walk-in helpdesk** → choose the event), with the
  team name in **Full name**, then **Confirm & generate ticket**. Use a different email for each, for example `yourname+garuda@gmail.com`
  or `yourname+malnad@gmail.com`. Every walk-in gets a ticket email. A walk-in
  has no member list, so "Who scored" shows only the captain.

The tournament page shows "Confirmed teams: 8" at the top. Cancelled,
waitlisted and unpaid registrations don't count.

Tip: register the teams in the sheet's order (Garuda Sena, Malnad Fighters,
Neuro Ninjas, Vajra, then Gaja Pade, Code Blue, Veera Yodha, Gandaberunda
Warriors). The pool boxes in part 4 then start filled in correctly: the first
four in Pool A, seeded 1–4, and the rest in Pool B.

## 3. Assign the coordinators (SPOC)

SPOC console → the event → **Assign Coordinator** → type the email (a new
email gets an account) → assign. Each coordinator now sees a green
**Matches & live scoring** button on the event's card on their dashboard.

## 4. Make the fixtures (SPOC)

SPOC console → the event → **Sports Tournament: Fixtures & Standings**.
In **Generate fixtures**:

| Field | Choose |
|---|---|
| Format | League then knockout (playoffs) |
| Win / Tie / Loss points | 5 / 3 / 0 |
| Close-loss points | 1 |
| Close loss = lost by at most | 7 |
| Each pair plays (league) | **Twice: home and away** |
| Pools | **Two pools, A and B** |

When you pick two pools, a box opens with every team. Set each team's pool
and seed number, as on the sheet:

| Pool A | Seed | Pool B | Seed |
|---|---|---|---|
| Garuda Sena | 1 | Gaja Pade | 1 |
| Malnad Fighters | 2 | Code Blue | 2 |
| Neuro Ninjas | 3 | Veera Yodha | 3 |
| Vajra | 4 | Gandaberunda Warriors | 4 |

Tick **An inter-pool round: A1 v B1, A2 v B2, …**, then press **Generate fixtures**.

You get 28 league matches, in the same order as the printed sheet:

- M-01 to M-12: Pool A, leg 1 and leg 2;
- M-13 to M-24: Pool B, leg 1 and leg 2;
- M-25 to M-28: the inter-pool round, A1 v B1 to A4 v B4.

An inter-pool win counts in each team's **own** pool table. The page shows
two tables, Pool A and Pool B.

> To fix a pool or seed, generate again with **Replace Fixtures**. Do this only
> before any match is played. Once the fixtures are made, a late team can't be
> added, because every match number would change. If a team pulls out, use
> **Replace** or **Withdraw** in the Teams card instead.

## 5. Logos and the schedule (SPOC)

**Logos.** In the Teams card, press **Add logo** next to a team and choose a
picture (PNG, JPG or WebP, up to 2 MB). The portal makes it a square and
keeps the whole logo. Logos appear in the tables, the fixtures and on the
scoreboard.

**Schedule (date, time, venue for all 31 matches at once):**

1. In the **Schedule** card, press the download link to get a CSV file
   with the columns Match, Stage, Team 1, Team 2, Date, Time, Venue.
2. Open it in Excel or Google Sheets. Fill Date (for example 2026-12-05 or
   05-12-2026), Time (15:30 or 3:30 PM) and Venue. Don't change the Match
   column.
3. Save it as CSV and press **Upload the schedule**.

If any row is wrong, nothing is changed, and the page says which row
(for example "Row 7 (M-06): …"). Fix that row and upload again. To change one
match, use **Save Schedule** on that match's card.

## 6. Scoring a match: who and how

**Who:** the SPOC, or any coordinator assigned to this event.
**Where:** coordinators use Dashboard → **Matches & live scoring**; the SPOC
uses the tournament page. Find the match (M-01 …) and press **Score live**.
A phone works best.

**During the match:**

1. Press **Start 1st half**. The clock starts at 20 minutes a half.
2. For each point, press the button on the side of the team that **got** the
   points. Every score has its own button, two a row, in three groups, with
   both teams side by side:

   | Group | Button | When |
   |---|---|---|
   | Raid points | **Raid +1 … Raid +7** | The raider touched that many defenders and got back (Raid +3 or more is a super raid) |
   | Raid points | **Bonus +1** | The raider crossed the bonus line |
   | Tackle points | **Tackle +1** | The defenders caught the raider |
   | Tackle points | **Super tackle +2** | Caught with 3 or fewer defenders on court |
   | Other points | **All out +2** | Every player of the other team is out |
   | Other points | **Technical point +1** | The referee gave a technical point |
   | Other points | **Out of bounds +1** | A player of the other team stepped out of the court |
   | Other points | **Do-or-die failed +1** | The other team's do-or-die raid scored nothing |

   A raid with touches **and** a bonus is two taps: for example **Raid +2**,
   then **Bonus +1**. A raid that makes an all out is the raid's points, then
   **All out +2**.

3. Pick the player in **Who scored (optional)** before the tap if you want
   top raider and top defender stats.
4. A wrong tap: press **Undo last**, or **Remove** next to it in **Last points**.
5. **Pause clock** and **Resume clock** for time-outs. Press **Half time**,
   then **Start 2nd half**.
6. At the end press **Full time: save the result**. The score goes into the
   table at once: 5 points for a win, 3 each for a tie, and 1 for losing by
   7 or fewer.

In a **semi-final or the final**, a tie must have a winner. Choose it in
**If it's a tie, who goes through** before Full time.

**Pressed Full time too early?** Open **Continue live scoring** and press
**Reopen the match**, or press **Clear the result** on the tournament page.

**No live scoring?** On the match's card, type both scores (and **If tied,
winner** for a playoff) and press **Save Result**. Use this if the network
fails or for a match scored on paper.

## 7. What the audience sees

- **Fixtures page:** `/tournament/fixtures/<event id>`. It has every match
  with its M-number, date, time and venue, both pool tables, logos and the
  champion. The event page shows the same tables.
- **Live scoreboard:** the **Public scoreboard** link on the scoring screen.
  It shows the score, the clock, the half and the logos, and updates by
  itself every few seconds. Put it on a projector or share it in the WhatsApp
  group.

## 8. Semi-finals, final, results and certificates (SPOC)

1. After M-28, on the tournament page, choose **Who plays off** →
   **Semi-finals: 1st A v 2nd B and 1st B v 2nd A, then the final**. Tick
   a third-place match if you want one. Then press **Make the playoffs**.
   - M-29 is SF1 (1st A v 2nd B); M-30 is SF2 (1st B v 2nd A).
   - M-31, the final, fills itself in when both semis are saved.
   - After this the league results are locked. If you pressed it too early,
     **Undo the playoffs** works until a playoff match is played.
2. Score the semis and the final the same way as in part 6.
3. Press **Publish results**. The winner, the runner-up (and third) become
   the event's results, and the champion shows on every page. If you fix a
   score later, press **Publish the corrected results**.
4. Mark attendance (Scanner → scan the tickets, or the Manual List). Then go
   to Certificates → Issue, for winner, runner-up and participation.

**Fix-it tools on the tournament page:** Rename a team, Replace a team,
Withdraw a team (its remaining matches become walkovers), Bring back,
"Fix this match" → **Give walkover** (a team didn't turn up), and
**Clear the result**. A coordinator can give a walkover too.

## 9. Demo run checklist (about 30 minutes)

1. Create "KPL Demo" (Sports tournament, Kabaddi, League then knockout).
2. Add 8 walk-in teams with the names above (part 2).
3. Assign yourself or a colleague as coordinator.
4. Generate: two pools, seeds as in the table, Twice, inter-pool ticked,
   points 5/3/0/1/7. Check that M-01 is Garuda Sena v Vajra.
5. Add one logo. Download the schedule, fill two rows and upload it.
6. On a phone, as the coordinator, **Score live** for M-01. Open the
   **Public scoreboard** on a laptop at the same time and watch it change.
   Try Undo and Half time, then Full time.
7. Quick-enter M-02 to M-28 with **Save Result**. Make one a 30–25 loss to
   see the close-loss point.
8. **Make the playoffs**. Check that SF1 is 1st A v 2nd B. Score both semis
   and the final, with one tie and a chosen winner.
9. **Publish results**, then look at the fixtures page and the event page.
10. Delete the demo event afterwards (SPOC console → **Delete Event Permanently**).
