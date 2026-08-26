# Operator's walkthrough

Getting from *"here's how I work"* to a running, routed, self-checking workspace.

Ten minutes, no methodology reading required. Every output below is copied from
an actual run against a live server, not written from intent.

**Architecture and rationale:** `architecture/ICM-VANCLIEF-BLUEPRINT.md`
**Deeper reference:** `agent-memory/` · `architecture/ICM-WORKSPACES.md`

---

## The one idea

Your folders *are* the app. Numbered folders carry the order, the hierarchy
scopes what an agent sees, and plain markdown holds the state. One agent reads
the right files at the right moment and does the work a multi-agent framework
would — and you can open any folder and see exactly what state the system is in,
because the state *is* the files.

Everything below is a consequence of that.

---

## 1. Describe your work

**Workspaces → 💬 Describe your work.** Write how you actually do the job, in
your own words. Don't try to sound structured:

> Every week I put out a client report. First I pull the numbers from the
> dashboard. Then I draft the commentary in our house voice. I always read it
> over and check the figures before it goes out. Finally I send it to the
> client.

It reads that back as a structure, citing the phrase behind each decision:

```
form:    Pipeline — a production line   (confident)
stages:  report · pull · draft · send
gate:    "I always read it over and check the figures…"
routes:  client · numbers · dashboard · commentary · house · voice
```

Note it got the stages *nearly* right — it picked up `report` from the opening
sentence, which isn't a step. **That is what the editable boxes are for.** Fix
them to `pull · draft · review · send` and press Create.

> **It can also tell you not to bother.** Type *"I use AI to fix my spelling"*
> and it refuses, with a reason: a workspace for a one-step job is scaffolding,
> not architecture. Use a saved prompt instead.

Result: a valid workspace, four stages, zero validation errors.

---

## 2. It's already reachable

You don't have to remember where anything lives. Ask for it:

```
"time for this week's client report"
  → matched  client-reports / 01-pull
    why: route: 'client'
```

**Workspaces → 🎯 Routing** shows the scoring for any phrase before you commit
to it, plus every workspace's declared triggers. If two workspaces match
equally it says **ambiguous** and asks, rather than guessing — starting in the
wrong folder is the one failure that looks completely normal while it happens.

To add a trigger, open that workspace's `CONTEXT.md` and add a bullet under
`## Routes`. That's the whole mechanism.

---

## 3. Capture from anywhere

**📥 Inbox** is one door. The pane, a hook, the terminal, an email, or your
phone's share sheet all write into the same folder.

For the phone: install the app to your home screen, then share to it from any
app. A share becomes a captured file and lands you back in the Inbox:

```
share → HTTP 303 → /?pane=inbox&captured=ok
```

Capture deliberately does **nothing else** — no routing, no AI call. You're
usually mid-something-else when you capture, and a capture that fails is a
thought you've lost.

---

## 4. Sweep the inbox

Press **Preview sweep** first. Nothing moves:

```
FILE   Q3 client numbers  →  client-reports / 01-pull
STAYS  what's the weather tomorrow  |  no-match
```

Then **Sweep now**: the matching item is written into the workspace stage as
markdown, and the unroutable one *stays in the inbox*. It is never filed
somewhere plausible — that would be wrong and silent. Anything swept moves to
`_filed/` with a record of where it went and why. Nothing is deleted.

If something you expected to file didn't, the inbox is telling you the target
workspace has no route for it. Add a trigger phrase (§2).

---

## 5. It checks itself

Workspaces drift — a contract gets deleted, a file gets moved. Delete a stage
contract and the folder tree tells you immediately:

```
FAILS THE WALK TEST
An agent will not be given this workspace's context until it is fixed.
  stages/02-draft has no CONTEXT.md, so it has no contract.
  → Add a CONTEXT.md to that stage declaring its Inputs, Process and Outputs.
```

And a chat turn against it is blocked rather than silently degraded:

```
route log:  blocked-walk-test  |  0 tokens
```

That matters more than it looks. Before this gate existed, a broken workspace
still logged `matched, 214 tokens` and the model answered from a structure with
its control point missing. Everything looked fine.

**Editing is never blocked** — that's how you repair it. Fix the file and the
next run works again. **Workspaces → 🔍 Audit a folder** walk-tests everything
at once.

---

## 6. Reuse what works

Once a shape proves out, **📐 Templates → Extract** turns it into a reusable
method:

```
Extracted 9 method files, left 1 output file behind.
```

It keeps the contracts, routing and reference material; it drops every output
file. So a template you share carries **no client data**. Five starters ship
with it — software feature, content pipeline, client records, second brain,
home & life ops — and *Use this* copies one into a new workspace.

---

## What to do first

1. **Describe one real recurring job.** Not your most complex — your most
   *repeated*. Correct the stages it proposes.
2. **Route it.** Add two or three trigger phrases and test them in the Routing
   tab.
3. **Put the app on your phone** and share something to it.
4. **Sweep once**, and read what stayed behind — that list is your routing
   telling you what it doesn't know yet.

Then leave it a week. The structure earns its keep on the second run, not the
first: you're configuring the factory, not the product.

---

## Quick reference

| I want to… | Go to |
|---|---|
| Turn a job into a workspace | Workspaces → 💬 Describe your work |
| See why a request went somewhere | Workspaces → 🎯 Routing |
| Check what past requests loaded | Workspaces → 📜 Route log |
| Reuse a proven structure | Workspaces → 📐 Templates |
| Map or reorganise an existing folder | Workspaces → 🔍 Audit a folder |
| Capture a thought or a link | 📥 Inbox (or your phone's share sheet) |
| Find out what's broken | Workspaces → 🔍 Audit a folder |

### For scripting

| Endpoint | Does |
|---|---|
| `POST /api/icm/describe` | Analyse a description. Creates nothing. |
| `POST /api/icm/describe/create` | Build the workspace it proposes. |
| `GET /api/icm/route?q=…` | Explain where a request would enter. |
| `POST /api/inbox` | Capture from any script or hook. |
| `GET /api/inbox/sweep/preview` | Where everything would go. |
| `POST /api/inbox/sweep` | File what routes; leave what doesn't. |
| `GET /api/icm/walk-test` | Every workspace's health, with repairs. |
| `POST /api/icm/index/rebuild-all` | Regenerate the file maps. |

### Four rules the system will hold you to

- **One stage, one job.** A stage that researches doesn't also write.
- **Every output is an edit surface.** Edit between stages; the next stage reads
  what you left.
- **Configure the factory, not the product.** Set it up once; each run reuses it.
- **Don't over-structure.** Chat → saved prompt → folders. Only climb when the
  rung below is genuinely repeating.
