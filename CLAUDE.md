# Doggos — project context

A daily rescue-dog digest for Edwin and Elizabeth: one email each morning listing
dogs that are newly listed, plus a filterable directory page.

- **Live site:** https://edwinbodge.github.io/doggos/
- **Repo:** `edwinbodge/doggos` (public — Pages is free only on public repos)
- **Cost:** $0. No server, no API keys, no scraping.

## What it's actually for

Edwin and Elizabeth are adopting a rescue dog in **January 2027**. They're in
Brooklyn now, relocating to Wisconsin. They want something **black-Lab-ish, 30–50
lb**, good with kids (they plan to have kids in 1–2 years and have a large
extended family) and good with other dogs.

The digest's "Top dogs" filter is looser than that on purpose: **≤60 lb, ≤5
years**, minus known disqualifiers. A small dog **under 1 year** still qualifies
on size, because a 24 lb six-month-old has growing to do.

This is a real tool someone checks every morning, not a demo. Correctness of the
dog data matters more than features.

## Layout

| File | Holds |
|---|---|
| `sources.py` | Five feed fetchers, the `Dog` dataclass, trait vocabulary |
| `digest.py` | Selection, email HTML, page build, SMTP delivery, CLI |
| `page_template.html` | The directory page; data injected at `/*__DATA__*/` |
| `.github/workflows/daily.yml` | Email + state, scheduled 11:23 UTC (runs hours late — see Operational notes) |
| `.github/workflows/site.yml` | Page refresh only, every 4 hours |
| `seen.json` | State: `{"first_seen": {dog_key: iso_date}}` |
| `assets/` | Favicon PNGs (Apple 🐶 emoji), copied into `docs/` every run |
| `docs/` | Published by Pages from `main` / `/docs` |

```bash
pip install -r requirements.txt pytest   # this Mac has no `python`; use a venv
python digest.py --dry-run     # build, write docs/, send nothing, save nothing
python digest.py --site-only   # refresh the page only, never touches state
python digest.py --test        # send one email now, change nothing
python digest.py --reset       # re-baseline (marks everything as seen)
python -m pytest test_sources.py -q
```

---

## Invariants — breaking any of these fails *silently*

Each of these is here because it already went wrong once, or would have.

**1. `--site-only` must never write `seen.json`.**
The site refresh runs every 4 hours; the email runs once a day. If a site refresh
recorded dogs as seen, the daily digest would find nothing new and **those dogs
would never be emailed** — the page would quietly eat the announcements. The
early return in `main()` sits deliberately before any state write. **Not
tested** — an earlier version of this note said it was; it isn't.

**2. A failed send must not advance the baseline.**
If the email didn't arrive, today's new dogs have to stay new so tomorrow
announces them. `send_failed` skips the state write and exits 1. The page still
publishes, and the workflow's commit step uses `!cancelled()` rather than
`success()` so the site doesn't go stale on exactly the mornings something broke.
Not tested.

**3. Petfinder needs `adoption_status: ["adoptable"]`.**
Without it the API returns the org's entire history. Labs4rescue came back with
600 dogs, all but 11 already adopted. This is the single easiest way to fill the
digest with dogs that went home months ago. Locked behind a regression test.

**4. Escape `<` in the page payload.**
Dog data is injected into a `<script>` block. `json.dumps` does not escape `<`,
so a rescue write-up containing `</script>` would close the tag and turn the rest
into HTML. Tested.

**5. If every source fails, abort before building anything.**
One bad source is survivable. With all five down, `dogs` is empty, and carrying on
would publish an empty directory over the real one and email "0 new doggos." (An
earlier version of this note said it would wipe the baseline — it wouldn't:
`first_seen` is only ever added to, never pruned.) The early return keeps the
page, the email and `seen.json` all untouched. Not tested.

**6. Empty env vars are not missing env vars.**
GitHub Actions expands an undefined `vars.X` to `""`, not to nothing. So
`os.environ.get("SMTP_PORT", "465")` returns `""` and `int("")` raises — this
took down a real run. Use the `env()` helper, which treats empty as absent.

---

## The five feeds

```
GET  mpr-public-api.uk.r.appspot.com/dogs                         Muddy Paws
GET  shelterluv.com/api/v3/available-animals/3447?species=Dog     Hearts & Bones
GET  petstablished.com/api/v2/public/search/shelter_show/1512552  Waldo's
POST psl.petfinder.com/graphql                                    Labs4rescue (CT178)
POST psl.petfinder.com/graphql                                    ACC Manhattan (NY12)
```

All unauthenticated public endpoints — the same ones the rescues' own sites call.
Petfinder's REST API stopped issuing keys in 2024; this is their public widget's
GraphQL endpoint, which needs no key. Shelterluv, Petstablished and Petfinder are
multi-tenant, so adding a rescue is one line in `SOURCES` given its org id.

Quirks already handled — don't rediscover them:

- Shelterluv returns `photos` as an object keyed by number, not an array, and
  `birthday` as a **string of digits** (a unix timestamp). An ISO-first date
  parser silently returns `None` on these and drops every dog from age filtering.
- Petstablished `public_url` is relative; some images are `.HEIC`, which browsers
  won't render.
- Petfinder wants `organization_id` (not `organization`), requires a `sort`
  argument, returns `null` for every image URL (build them from `_media` ids plus
  the CDN base), puts `sex` on `physical` rather than top level, and reports a
  global `totalCount` rather than a filtered one.
- Muddy Paws shows 71 dogs: 65 `Available` plus 6 `Waitlist Full / Pending
  Adoption`. Both are kept so nothing silently disappears; waitlisted ones get a
  chip and are held out of Top dogs.

---

## Design decisions worth not re-litigating

**Traits are ranked, not hard-filtered.** Only Hearts & Bones publishes
good-with-kids/dogs as structured data. Filtering strictly on "must have both"
would make Top dogs a Hearts & Bones–only list and hide four of the five rescues.
So: hard-filter on size and age (universal), exclude known disqualifiers, then
*rank* confirmed-good first with unknowns below, marked "traits not listed."

**Descriptions are mined for traits.** ACC writes to a house style and embeds
exact weight and age in prose (`Weight: 48lbs`, `Age: 1yrs 0mths`) — better than
Petfinder's size buckets. Waldo's and Muddy Paws yield phrases like "great with
kids" and "should be the only dog." A negative statement always overrides a
positive one.

**Sorting uses `first_seen`, not the rescues' listing dates.** Only Hearts &
Bones publishes a real listing date and theirs run months back — sorting on a mix
would bury every Hearts & Bones dog while dateless ACC dogs floated to the top.
`first_seen` is the one date every source gives us and is the honest reading of
"newest to me." Dates the rescue didn't provide render with a `+` (`Listed 26d+`)
because they're a floor, not the truth.

**Two fonts, five type roles.** Serif for the page headline and dog names only;
sans for everything else. No third family, no mono — `tabular-nums` handles
number alignment.

**Email is table-based with one `<style>` block.** A 480px breakpoint stacks the
photo full-width with text below, matching the site. If a client strips the
block, it degrades to the desktop two-column layout. Note the card needs an
explicit `width:100%` on mobile — the `width="600"` HTML attribute beats
`max-width` on a narrow viewport.

---

## Email delivery — the unresolved part

Currently **Gmail SMTP** with an app password, sending from a throwaway Gmail
account created for this. `digest.py` speaks plain SMTP, so switching providers
needs **no code change** — only `SMTP_HOST` / `SMTP_PORT` (Variables) and
`SMTP_USER` / `SMTP_PASSWORD` (Secrets).

### What happened on 14 September

Worth knowing in full, because the instinct to "fix the credential" is wrong.

The morning run failed with `SMTPAuthenticationError: 534 5.7.9
WebLoginRequired`. The account's security log showed why (times Central):

```
 5:10 AM   Your account was disabled     ← no location, no device (automated)
 6:23 AM   digest scheduled
11:58 AM   digest actually runs (16:58 UTC, 5h35m late), gets 534
 2:42 PM   Account restored              Wisconsin
 2:51 PM   manual re-run succeeds
```

Google had **disabled the whole account** almost seven hours before the run. (An
earlier version of this timeline put the run at 6:23 — that was the cron time,
not when it ran.) The SMTP
rejection was the symptom, not the cause. Two wrong turns were taken diagnosing
it: first attributing it to gradual IP-based risk scoring (it was a single
discrete enforcement action), then concluding the app password had been
invalidated (it hadn't — "last used Sep 13" was right there, and re-running after
the restore worked immediately). Also note `accounts.google.com/DisplayUnlockCaptcha`
has been **retired** — it no longer works as an unblock step.

Likely cause, though Google doesn't say: the account was created 10 Sept and its
entire history was a once-daily SMTP login from a rotating Azure datacenter IP,
often a different country, with zero human browser activity. That profile closely
matches a compromised or botted account.

### The open decision

The usage pattern that got it disabled hasn't changed, so this may recur.
Mitigations already applied: recovery phone added; sign into the account in a
browser occasionally to give it human signal. Current research on alternatives
(as of Sept 2026 — verify before acting, these tiers change constantly):

- **SendGrid's permanent free plan is gone** (60-day trial only).
- **Amazon SES killed its free tier** in July 2026.
- Still free-forever with SMTP: Brevo (300/day), Mailjet (6,000/mo), SMTP2GO
  (1,000/mo), Mailgun (100/day), MailerSend (500/mo), Postmark (100/mo).

Volume is irrelevant — this sends one email a day. The real constraint is the
**From address**. Without owning a domain you must verify a single sender (a
gmail.com address), and SPF/DKIM then won't align with gmail.com, which risks the
spam folder. SMTP2GO refuses single-sender verification outright for domains
publishing DMARC, and gmail.com does.

Three live options, Edwin has not yet chosen:

1. **Mailgun sandbox** — auto-provisioned, no domain, no card, but capped at **5
   authorized recipients**. That cap is normally fatal and here is fine: there are
   two recipients. Sender is Mailgun's own domain, so alignment is correct and
   there's no spam risk. Ugly from-address.
2. **Brevo with a verified gmail sender** — normal-looking, slight spam risk,
   room to grow past five recipients.
3. **Buy a domain (~$10/yr)** — verify once anywhere, alignment is correct
   forever, question never returns.

---

## Operational notes

- **Petfinder blocks this Mac.** From Edwin's home connection `psl.petfinder.com`
  returns `403 Access Denied` (an edge block, HTML not JSON), so local runs log
  `Labs4rescue FAILED` / `ACC Manhattan FAILED` and build a page missing ~100
  dogs. CI's runners get through fine. Don't commit a locally built `docs/` — let
  the workflows publish, or trigger "Refresh site" by hand.
- **GitHub cron is best-effort, and here it's late every day.** Every scheduled
  digest so far:

  | Date | Cron (UTC) | Started (UTC) | Late |
  |---|---|---|---|
  | 11 Sep | 11:00 | 14:40 | 3h40m |
  | 12 Sep | 11:23 | 14:13 | 2h50m |
  | 13 Sep | 11:23 | 14:56 | 3h33m |
  | 14 Sep | 11:23 | 16:58 | 5h35m |

  So the "morning" email realistically lands 10am–1pm Eastern. The `:23` minute
  was meant to dodge the `:00` queue; on four runs it hasn't clearly helped.
  Check with `gh run list --workflow daily.yml --event schedule` before assuming
  a late email means something broke.
- Both workflows share a `concurrency` group and `git pull --rebase` before
  pushing, because both push to `main`.
- GitHub disables scheduled workflows after **60 days of repo inactivity**. The
  daily commits keep it awake; a long quiet stretch is the explanation if it
  stops.
- The site is **public** — anyone with the URL can read it. Keep personal notes
  off it. The per-browser hidden-dogs list lives in `localStorage` and never
  leaves the device, which is why Edwin and Elizabeth keep separate lists.
- `docs/.nojekyll` is written every run. Without it Pages runs the folder through
  Jekyll, which builds nothing useful here and drops files starting with `_`.
  The favicons are copied from `assets/` on every run for the same reason — so a
  fresh clone or a deleted `docs/` can't lose them.

## Working style

Edwin is a former product leader and reads the reasoning, not just the result.
Worth matching what's worked so far:

- **Verify against the real thing rather than asserting.** Several bugs here were
  found only by rendering the page at 390px, parsing the actual payload, or
  fetching the run history from the API. Claims that "the markup looks right"
  have been wrong more than once.
- **Say plainly when something was wrong**, including your own earlier calls.
  Three diagnoses in this project were corrected after the fact.
- **Reproduce before fixing.** The send-failure and empty-env-var fixes were both
  validated by simulating the exact failure first.
