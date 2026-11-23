# Running the Sapthagiri Kabaddi Premier League on the portal

This guide follows the Season-1 fixture sheet: 8 teams in two pools, home and
away in each pool, an inter-pool round, semi-finals across the pools, and a
final. That is 31 matches, M-01 to M-31. Do a demo run first (part 9), then
the real event.

## Who does what

| Person | What they do on the portal |
|---|---|
| **SPOC** (the event's owner) | Creates the event, assigns the coordinators, makes the fixtures (pools, seeds, home and away), adds team logos, uploads the fixture sheet (teams, dates), makes the playoffs, publishes the results, issues the certificates. Can also score any match. |
| **Coordinator** (assigned to this event) | Scores matches live from a phone, or types in a final score. Postpones a match or puts it back on. Checks teams in at the gate. Can't change the fixtures, the pools, the schedule or the logos. |
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
  team name, a clear **team logo** (PNG, JPG or WebP, up to 2 MB, at least
  200 × 200 pixels) and every player's name and **jersey number**, their own
  included (0 to 999; two players may share one). The logo shows beside the team's name
  on the scoreboard, the big screen, the fixtures and the tables; the jersey
  number shows beside each player's name in the scorer's lists and the
  top raiders and defenders. The members' names fill the
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
| Points rule | **PKL Season 12: win 2, loss 0, a tie goes to the tie-breaker** |
| PKL mode | **Ticked**: matches are scored raid by raid (part 6) |
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

**The points rule.** PKL Season 12 has no ties in the table: a win is 2
points, a loss 0. A match level at full time goes to the **tie-breaker**:
5 raids each (7 defenders every raid, the baulk line counts as the bonus
line), then a **golden raid** if it is still level (the referee's coin toss
if that is level too). The tie-breaker's winner takes the 2 points. The older
rule (5 a win, 3 a tie, 1 for losing by 7 or fewer) is still in the list;
pick it to type your own numbers. **Change the points rule** under the
tables switches either way later, without new fixtures.

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
keeps the whole logo. Logos appear in the tables, the fixtures, the
scoreboard and the big screen. The eight logos from the fixture PDF are in
the `kpl-team-logos` folder in Downloads, named A1 Garuda Sena … B4
Gandaberunda Warriors. A logo the captain uploaded when registering is
already there; one you add here replaces it.

**Teams that registered before the logo and jersey numbers were asked.**
Their players have no jersey number yet. On the tournament page, **Jersey
numbers** lists every team and player on one page: type the numbers and
**Save jersey numbers** once. A number two players of a team share is marked
"same number" but saved. The numbers show on the scorer's phone and the
boards at once, and in the line-ups of matches not yet over (a finished match
keeps the numbers it was played in). One team at a time works too:
Coordinator → **Registrations** → the team → **Edit**. Give these teams
their logo with **Add logo** above.

**The fixture sheet: who plays each match, and when (Excel or CSV):**

1. In the **Fixture sheet** card, download it as **Excel** (or CSV). It has
   every match: Match, Stage, Team 1, Team 2, Date, Time, Venue.
2. Change **Team 1** and **Team 2** to the teams that play that match,
   spelled as they registered (capitals and extra spaces don't matter).
   Date, Time and Venue can stay empty: there is no fixed time, a match
   plays when the coordinator starts it.
3. Press **Upload the fixture sheet** with the .xlsx (or .csv) file.

Your own sheet works too: it needs a **Match** column (M1, M-01 or 1) and
**Team 1 / Team 2** (or Team A / Team B, Home / Away). A title row above the
header is fine. Rows for M-29 to M-31 are skipped: the semi-finals and the
final are made by **Make the playoffs** from the pool tables.

If any row is wrong (a team name not on the list, a match already played, a
team against itself), nothing is changed and the page names the row, for
example "Row 7 (M-06): no team is called …". Fix it and upload again. To
change one match, use **Fix this match → Set the teams** or **Save
Schedule** on its card.

**Postponed.** A match that can't be played yet: **Fix this match →
Postpone this match** (the SPOC or a coordinator). It shows "Postponed" on
every page and the big screen skips it for "Up next". **Back on: play it
now** undoes it; starting it for live scoring or saving its result does too.

## 6. Scoring a match: who and how

**Who:** the SPOC, or any coordinator assigned to this event. Nobody else
can score: a volunteer, a judge, a student or a coordinator of another event
gets "not allowed", and the audience only sees the scoreboard.
**Where:** coordinators use Dashboard → **Matches & live scoring**; the SPOC
uses the tournament page. Find the match (M-01 …) and press **Score live**.
A phone works best. The scoring page has **How to score this match** under
the score: the steps below, for the mode the match uses. It is open before
the match starts and folds away once it has started (tap it to open it again).

**PKL mode or point by point.** With **PKL mode** on (part 4, or the switch
under **Big screen and the road to the final** on the tournament page), you
tap how each raid ended and the portal works out the points. With it off, you
tap the points (the buttons below). The switch counts for matches opened for
scoring after the change; a match already being scored keeps its way. If PKL
mode feels slow for your scorers, turn it off: point by point always works.

**PKL mode, raid by raid:**

1. Choose **Who raids first (won the toss)**, then **Start 1st half**.
2. The panel shows both teams' players on the mat (green dots), whose raid it
   is (**Raid 7: Vajra**), and **DO-OR-DIE**, **Bonus line live** and
   **Super tackle on** when they apply.
3. When the raid ends, tap one button:

   | Button | When | What the portal does |
   |---|---|---|
   | **1 touch … 7 touches** | The raider touched that many and got back | Raid points; those defenders out; as many of the raider's team revived; the last defender out is an **all out** (+2, the team back to 7) |
   | **+ Bonus** (tick first) | The raider also crossed the bonus line | +1 more; only with 6 or more defenders |
   | **Bonus only +1** | Bonus line, no touch | +1 |
   | **Empty raid** | Nothing happened | Counted; a team's third raid after two empty ones is **do-or-die**: empty then means the raider is out and +1 to the defence |
   | **Tackled +1 / Super tackle +2** | The defenders caught the raider | +1, or +2 with 3 or fewer defenders; the raider out |
   | **Raider out of court** | The raider stepped out | Raider out, +1 to the defence |

   Pick the raider (and the tackler) in the lists first if you want player
   stats. The turn passes to the other team by itself; in the 2nd half the
   other team raids first.
4. **Calls** (open the line under the buttons), for each team: **Technical
   point +1**, **Their player out of bounds** (the other team +1, the player
   out), **Time-out** (2 a team in each half; the clock stops, press
   **Resume clock**), **Review upheld / not upheld** (logged; if it changes a
   call, Remove that raid and enter it again), **+1 / −1 on the mat** (put the
   count right), and **Other team raids** if the referee gives the raid to the
   other side.
5. A wrong tap: **Undo last**, or **Remove** next to any raid in **All
   points**. The match is worked out again from the raids, so the mat, the
   do-or-die count and the score stay right.

**Point by point (PKL mode off):**

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
5. **Pause clock** and **Resume clock** for time-outs and reviews. Press **Half time**,
   then **Start 2nd half**.
6. At the end press **Full time: save the result**. The score goes into the
   table at once (Season 12: 2 for a win, 0 for a loss).

**A tie (Season 12).** At a level score, **Full time** starts the
**tie-breaker** on the scoring screen, in either mode: choose the raiding
team for the first raid, then tap each raid (touches, bonus, empty, tackled);
the teams take turns, 5 raids each. If it is still level, tap **Golden raid
won by …** (or **Coin toss won by …**). Then press **Full time: save the
result**. The table gives the winner 2 points, and the match shows "Vajra
won the shootout 4–3". **Back to the 2nd half** undoes a Full time pressed
by mistake before the first tie-breaker raid; **Undo last** takes back a
tie-breaker raid.

With the **older rule**, a league tie stays a tie; in a **semi-final or the
final** choose the winner in **If it's a tie, who goes through** before Full
time.

**Pressed Full time too early?** Open **Continue live scoring** and press
**Reopen the match**, or press **Clear the result** on the tournament page.

**No live scoring?** On the match's card, type both scores (for a tie also
**If tied, winner**, and with Season 12 **Tie decided by** and the shootout's
score) and press **Save Result**. Use this if the network
fails or for a match scored on paper.

## 7. What the audience sees

- **Big screen (for the hall):** `/tournament/screen/<event id>`, also the
  **Open the big screen** button on the tournament page and **Big screen**
  on the scoring page and the fixtures page. No login. It shows the match
  being scored (logos, score, clock, raid and tackle points, the last three
  points), or **Up next** and the last result between matches; both pool
  tables with the top two marked; the **Road to the final**; the top raiders
  and defenders; with PKL mode, whose raid it is, DO-OR-DIE and the players
  on the mat; during a tie-breaker, its score. It updates itself every 2
  seconds. The college logo is at the top, with a **QR code**: the audience
  scan it and the fixtures page opens on their phones, with the matches being
  played at the top (**Watch the score live**).
- **Fixtures page:** `/tournament/fixtures/<event id>`. At the top, **Choose
  a pool**: the buttons **All**, **Pool A** and **Pool B**, and each pool's
  teams with their logos and seeds (A1 … A4, B1 … B4), so everyone can see
  which team is in which pool. **Pool A** shows only Pool A's table, its
  matches, the inter-pool round and the playoffs, and only Pool A's players'
  points; **Pool B** the same for Pool B. The link with the pool chosen
  (`…?pool=A`) can be shared on its own. **All** shows every match,
  both pool tables, the road to the final, the top raiders and
  defenders, and **Every player's points** team by team (raid, tackle,
  total, matches, Super 10s, High 5s): this is where players see their own
  progress. Share this link in the WhatsApp group: the preview shows the
  college logo and the event's name.
- **Live scoreboard for one match:** the **Public scoreboard** link on the
  scoring screen.

**Putting the big screen on a monitor or projector:**

1. Join the laptop to the monitor or projector with an HDMI cable (a Mac may
   need a USB-C to HDMI adapter). On a smart TV you can cast a Chrome tab
   instead (Chrome menu → Cast).
2. Choose "Mirror" or "Duplicate" display (Windows: Win+P → Duplicate; Mac:
   Control Centre → Screen Mirroring), so you see what the hall sees.
3. Open the big-screen link in Chrome and press **Full screen** on the page
   (or F11 on Windows, Ctrl+Cmd+F on a Mac).
4. Keep the laptop on charge. The page asks the browser to keep the screen
   awake; also set the laptop's sleep to "Never" for the day.
5. Use a different device (a phone) to score. If the Wi-Fi drops, the screen
   shows "Connection lost" and keeps the last score; it carries on by itself
   when the network is back.

**The road to the final** is on the tournament page, the fixtures page and
the big screen: SF1 (1st Pool A v 2nd Pool B), SF2 (1st Pool B v 2nd Pool A),
the final and the champion. Until the playoffs are made it shows who would
meet if the league ended now (dashed boxes), changing with every result.

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
   PKL Season 12, PKL mode ticked. Check that M-01 is Garuda Sena v Vajra.
5. Add one logo. Download the fixture sheet as Excel, swap the teams of two
   matches and upload it. Postpone M-03 and put it back on.
6. Open the **big screen** on a laptop. On a phone, as the coordinator,
   **Score live** for M-01 and watch the big screen change. Make a team
   do-or-die (two empty raids) and an all out. Try Undo and Half time, then
   end it level and play the tie-breaker. Scan the big screen's QR code with
   another phone.
7. Quick-enter M-02 to M-28 with **Save Result**. Make one 30–30 with a
   shootout winner to see it in the table.
8. **Make the playoffs**. Check that SF1 is 1st A v 2nd B. Score both semis
   and the final, with one tie and a chosen winner.
9. **Publish results**, then look at the fixtures page and the event page.
10. Delete the demo event afterwards (SPOC console → **Delete Event Permanently**).

## 10. On the day: run order

**The day before**

1. Register the 8 teams (part 2): the captain gives the team logo and every
   player's name and jersey number; the team is confirmed at once and the
   players get no email. Teams that registered earlier: add their jersey
   numbers on Registrations → Edit and their logos with Add logo (part 5).
2. Assign the coordinators (part 3).
3. Make the fixtures (part 4), add the logos, and upload the fixture sheet
   if any match's teams differ from the draw (part 5).
4. Open the big screen on the hall laptop once to check it shows both pool
   tables and "Up next: M-01".

**On the day**

1. Hall laptop: big screen, full screen, on charge.
2. Each coordinator: Dashboard → **Matches & live scoring** → the match →
   **Score live** → **Start 1st half**. Points as in part 6, Half time,
   2nd half, **Full time: save the result**. The tables, the road to the final
   and the big screen update by themselves.
3. A match that can't go ahead: **Postpone this match**; play the next one.
4. After M-28: **Make the playoffs** (part 8), score M-29, M-30 and the final.
5. **Publish results**, then the certificates.
