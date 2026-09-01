# Assignment 02 — Inventory & Stock Control

## The scenario

Picture a small distributor moving physical goods through a handful of locations — a main warehouse
and a couple of retail floors, or a scatter of project sites — with the same popular items
constantly coming in, going out, and sometimes moving from one location to another. Right now none
of that lives in one place. Whoever receives a delivery updates a spreadsheet if they remember to, a
phone call substitutes for a record when stock moves between locations, and the number in the
spreadsheet and the number on the shelf quietly drift apart within a week.

The result is predictable. A location runs out of a fast-moving item mid-week and nobody notices
until a customer asks for it. Someone "fixes" a miscount by typing a new number directly into the
spreadsheet, and a month later nobody can reconstruct what actually happened to the missing units. A
transfer between two locations gets logged at the sending end but never at the receiving end, so one
location's count runs permanently short and the other permanently long, and reconciling it means
someone physically recounting shelves.

They want one system where every unit that arrives, leaves, or moves between locations is recorded
as it happens, so the number on hand is always just the sum of what was actually recorded — never a
number someone typed in directly. Staff at each location record their own day-to-day movements, and
whoever is responsible for purchasing can see, at a glance, what is about to run out before it does.
That is what you are building.

## What it must do

Everything below is required. Several of the ten spell out exact rules — what happens on an illegal
move, what a bulk action must report back, when a dismissed alert is allowed to reappear — and those
specifics are the actual ask, not just the bold headline in front of them.

1. **Accounts and roles.** People sign in with an email and password, and there are at least two
roles — an inventory manager role and a warehouse staff role. Managers can create and archive items,
create locations, set reorder levels, record any kind of stock movement including adjustments, and
decide which staff are assigned to which locations. Staff can record receipts, issues and transfers
only at the locations they are assigned to, and cannot create items, locations or adjustments. The
difference must be enforced on the server, not just hidden in the interface.

2. **Items.** Managers create items with a SKU, a name, a description, a unit of measure, a reorder
level and a category, and can edit them later. Categories are a short list that managers maintain,
not free text typed per item. Items can be archived and restored. Archiving removes an item from
day-to-day lists and blocks new movements against it, without destroying its movement history.

3. **Stock movements.** Every stock movement belongs to exactly one item and records a kind —
receipt, issue, transfer or adjustment — a quantity, a location, and who recorded it. A transfer
additionally records both the source and destination location. Movements can be recorded against an
item at any time, and opening an item shows its full movement history in order.

4. **The stock ledger.** Stock movements form an append-only ledger: once a receipt, issue, transfer
or adjustment is recorded, it can never be changed or removed. An item's on-hand quantity is never
stored or edited directly — it is always derived by summing its ledger entries. A transfer moves
stock from one location to another as a single indivisible operation, and the server refuses any
transfer that would drive either location's quantity negative. Every adjustment must carry a reason,
and the server rejects one submitted without it.

5. **Location assignment.** Any staff member can be assigned to any number of locations they are
responsible for, and a location can have any number of staff assigned to it. Only a manager can
create or change these assignments. Staff can only record movements at locations they are assigned
to, while managers can act at every location.

6. **Finding items.** One list shows every item, with a text search over name and SKU, filters for
category, location, archived status and at-or-below-reorder, sorting by name, on-hand quantity or
reorder level, and pagination showing the total number of matches. All of this must happen on the
server — do not load every item into the browser and filter there.

7. **Bulk import and export.** Items can be bulk-imported from a CSV file, and so can bulk stock
receipts. Each import returns a per-row report naming exactly which rows failed and why, while still
importing every row that was valid rather than rejecting the whole file over one bad line.
Separately, export the current stock position — every item's on-hand quantity by location — as a CSV
file.

8. **A dashboard.** A landing view shows headline numbers — active items, items at or below reorder
level, movements recorded today, and distinct items moved this week. It also breaks on-hand stock
down by category and by location, and charts receipt and issue volume over the last eight weeks.

9. **History you cannot rewrite.** Every item has a timeline showing when it was created, every
field change — name, category, reorder level — with the old and new value and who made it, and any
notes staff leave about it. Notes are part of this timeline, the same as field changes. Nothing in
it can be edited or deleted after the fact, including by managers.

10. **Low-stock alerts.** Any item whose on-hand quantity, summed across every location, falls at or
below its configured reorder level appears in a low-stock alerts area, with a count badge visible in
the navigation. A manager can dismiss an alert for a specific item. If that item's on-hand quantity
later rises above the reorder level and then falls back at or below it again, the alert reappears.

## Stretch ideas (optional)

None of these are required, and none substitute for a goal above. If you finish all ten with time
left over, pick whichever of these sounds most useful and build it:

- Barcode-friendly SKU lookup for fast entry.
- Reorder suggestions with a recommended order quantity.
- Multiple units of measure with conversion between them.
- Cycle counts with a variance report against the ledger.
- Supplier records linked to items.
- A low-stock email digest.
- Serial or batch/lot number tracking on movements.
- A print-friendly pick list for outgoing orders.
- Printable location labels.


---

## What we are assessing

A working application is table stakes. Almost every serious candidate will produce something that runs, has a login, and roughly does what was asked. That's the floor, not the differentiator.

What actually separates submissions is the record of thinking behind the app: the decisions you made and why, the trade-offs you weighed, what you built first and what you deliberately left out, and whether you can explain any part of your own system when asked. We are hiring for judgement. The app is the evidence for that judgement, not the deliverable in itself.

We also read the code itself for structure and readability, which counts for a small share of the overall score.

## Time budget

Budget about 12 hours total, spent roughly 2 hours a day across a week.

This is not a race. We are not timing you against other candidates, and submitting early scores nothing extra. Twelve hours is a size guide so you know how much to attempt — pace yourself, stop when you're tired, and spend some of that time thinking and documenting, not only typing code.

## Pick any stack you like

Use any language, any framework, any UI library, any ORM, and any database access approach you want. We have no house stack, and no stack scores better than another — this round is not a test of whether you know particular tools.

Use whatever you are fastest and most confident in. Time spent learning something new to impress us is time not spent on the ten goals above, and it will show.

## Using AI is allowed and encouraged

Use AI tools however you want — to scaffold code, debug a stuck problem, write tests, draft documentation, or anything else that helps you move faster. A few things to know about how we treat it:

- We do not penalise AI use, and we make no attempt to detect it.
- We care about whether you understood, directed and verified the output — not about who or what produced the first draft of it.
- `docs/ai-prompts.md` must contain the prompts you actually used, including the ones that produced bad output and what you changed afterwards. If you used no AI at all, say so here and describe how you worked instead — that is assessed the same way.
- Submitting generated code you cannot explain is the single most common way candidates fail this round.

You are accountable for everything in your submission. If a reviewer points at a piece of code and asks why it's there, or why it works the way it does, "the AI wrote it" is not an answer.

## Use git properly

Publish to a public GitHub repository, and commit incrementally as the work actually happens — after each meaningful step, not in one pass at the end.

A repository whose entire history is a single "initial commit" containing a finished app scores zero on git history, and it colours how we read everything else in your submission, however good the app itself is. Your history is how we see the order you built in, where you got stuck, and how the design changed along the way. If it isn't there, we can't assess it, and we won't assume the best.

## What you must commit

Alongside your code, commit these five files under `docs/`. Your zip includes a stub for each with the questions it needs to answer — fill them in as you go, not from memory at the end.

| File | What it must answer |
|------|----------------------|
| `docs/architecture.md` | What the moving pieces are, how they talk to each other, where each one runs, the request path for one representative user action end to end, and what you decided not to build. |
| `docs/schema.md` | Every table's columns and types, which relationships are one-to-many versus many-to-many, which constraints live in the database versus the application, what you deliberately denormalised, and what would break first at 100x the data. |
| `docs/plan.md` | How you split the work into sessions, what order you built in and why, what you estimated versus what it actually took, and what you cut when you ran short. |
| `docs/decisions.md` | At least five real decisions — what you chose, what you rejected, and why — including at least one you later reversed. |
| `docs/ai-prompts.md` | The prompts you actually used, in order, grouped by what you were trying to do, including at least one that produced something wrong and what you did about it. |

## Host it for free

Deploy the whole thing somewhere reachable by URL, using free tiers only.

One combination that works, if you would rather not decide:

- **Database** — a managed service such as Supabase.
- **Server-side code** — Render.
- **Browser-side code** — Vercel.

Deploy in that order: create the database first, give the server its connection details as environment variables, then point the browser-side part at the server's public URL.

This is one option, not a requirement. Any free host is equally acceptable — everything on a single provider, one virtual machine, a container platform, a static host with serverless functions. The choice earns and loses nothing.

Requirements:

- A working live URL.
- Seeded with enough demo data to show the system doing something, not an empty shell.
- Demo credentials for every role recorded in `SUBMISSION.md`.
- Connection strings, keys and passwords kept in environment variables, never in the repository.
- Free tiers often sleep when idle and can take a minute or more to wake. Note it in `SUBMISSION.md` if yours does, so a slow first load is not read as a broken deployment.
- If you cannot get it hosted, submit anyway and record in `SUBMISSION.md` what you tried and where it broke.

## How to submit

Send us:

- The URL of your public GitHub repository.
- The URL of your live, deployed application.
- Your completed `SUBMISSION.md`, committed to the repository.

That's the whole submission. Nothing else to prepare, no separate form.

## What happens next

If your submission clears the bar, we'll set up a short call. We will ask about specific decisions we can see in your repository and its history — why you modelled something a particular way, what a certain commit was fixing, what you'd change if you kept going.

We're telling you this now because it should change how carefully you document as you go. Write `docs/decisions.md` for a version of yourself who has to explain it three weeks from now.

## Scope

The 10 goals stated in this brief are the cutoff. Meet all 10, solidly, and you have a complete submission.

Stretch ideas are optional. They exist for candidates who finish the 10 with time left and want to keep building — they are never required, and they do not make up for a goal you didn't hit. Doing 8 goals well beats doing 10 goals badly. If time is short, finish fewer goals properly rather than leaving all ten half-done.
