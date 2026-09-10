# Doggos — a daily rescue digest

Every morning: fetch all five rescues, work out which dogs are new, email you and
Elizabeth **"X new doggos for you"**, and republish a filterable directory page.

No API keys, no scraping, no server. Runs free on GitHub Actions.

---

## Setup

**[SETUP.md](SETUP.md)** walks through it end to end — the agent Gmail account,
the GitHub repo and Pages, the secrets, and the security notes worth reading
before you push. About 30 minutes, once.

The short version: new Gmail → app password → push this repo public → Pages from
`main` / `/docs` → four secrets and one variable → run the workflow once by hand
to set the baseline.

---

## What's in the email

**New today** — everything not listed yesterday, unfiltered by design so nothing
slips past. Each dog carries its trait chips: green for good-with-kids and
good-with-dogs, plain for housetrained and crate-trained, gold for
foster-to-adopt, and orange for the warnings that matter to you — solo-dog-only,
adult-home-preferred, needs-a-quiet-home.

**Top dogs** — under 60 lb, five years or younger, nothing flagged as needing an
adult-only or solo home, confirmed good-with-kids-and-dogs ranked first. Small dogs
count too if they're **under a year**, since a 24 lb six-month-old still has growing
to do.

**Top labs** — the same filter against Labs4rescue.

**The order of Top dogs is shuffled daily.** Seeded by the date, so it's stable if
you reload but different tomorrow — otherwise the same handful live at the top
forever and you never look at what's below them.

**Browse all** — a button at the top *and* bottom, through to the directory.

## The directory page

One list of every dog, with four one-click presets — **New this week**, **Closest
fit**, **Top labs**, **All dogs** — and a **Custom search** panel underneath:
rescue, max weight, max age, sex, how recently listed, plus toggles for good with
kids, good with dogs, housetrained, crate-trained, foster-to-adopt, Labs only, and
hide-anything-with-warnings. Presets just fill in that same panel, so you can click
one and then adjust. Your last filter is remembered per device.

**Hiding dogs.** The eye button at the bottom-right of each card hides that dog —
it drops to the end of the list rather than vanishing, and the count line says how
many are hidden. This lives in `localStorage`, so it's per browser: you and
Elizabeth each keep your own list and neither sees the other's.

**How long a dog has been listed.** Only Shelterluv publishes a real intake date,
so Hearts & Bones dogs read `Listed 34d`. Everyone else gets a `+` — `Listed 26d+`
means *at least* that long, counted from the first morning this digest saw them.
Petfinder, Muddy Paws and Petstablished expose no listing date at all; I checked.
ACC sometimes says "long stay pup" in the write-up, which becomes a **Long stay**
chip and is the closest thing to a real signal for a dog that isn't moving.

---

## About the "good with kids and dogs" filter

Worth knowing, because it shapes what you see:

| | good w/ kids | good w/ dogs | housetrained | warnings |
|---|---|---|---|---|
| Hearts & Bones | ✅ structured | ✅ structured | ✅ | ✅ |
| ACC Manhattan | ✅ *from prose* | ✅ *from prose* | ✅ | ✅ *from prose* |
| Muddy Paws | ❌ | ❌ | ❌ | ✅ rich |
| Waldo's | ❌ | ❌ | ❌ | minimal |
| Labs4rescue | ❌ | ❌ | ✅ | ❌ |

**Only Hearts & Bones publishes those as structured data** — everything in the ACC
row above is parsed out of their write-ups, not read from a field. Filtering
strictly on "must have both" would have made Top Dogs a Hearts & Bones–only list
and quietly hidden four of your five rescues.

So it works in three steps instead:

1. **Hard filter** on what every source gives — size and age
2. **Exclude** anything with a known disqualifier
3. **Rank** confirmed-good to the top; in-spec dogs whose rescue simply doesn't
   publish traits sit below, marked *traits not listed*, so you never miss one

Muddy Paws is the interesting case: their vocabulary is exception-based. They
never write "good with kids," but they do write "Adult home preferred" and "Best
fit as solo dog." Absence of a warning is real signal there.

### ACC is the richest text source

ACC writes to a house style, and every one of their 97 dogs checked had **exact
weight and exact age embedded in the prose** — `Weight: 48lbs`, `Age: 1yrs 0mths
3wks` — which the digest parses out. That beats Petfinder's Small/Medium/Large
bucket and makes the 60 lb and 5 year cuts precise for ACC dogs.

Their compatibility sentences are near-verbatim across listings, so they parse
reliably:

| ACC sentence | becomes |
|---|---|
| "I lived with children in my previous home." | Good with kids |
| "I have lived with dogs in my previous home." / "I am a playgroup rockstar!" | Good with dogs |
| "I would do best in a home with only adult humans." | Adult home preferred |
| "…without very tiny humans…" | Adult home preferred |
| "I need a home where there are no other dogs." | Not good with dogs |
| "I would appreciate slow introductions…" | Slow to warm up |
| "I don't always like to share my food, toys…" | Guards food or toys |
| "I have medical needs that staff will address…" | Has medical needs |

The last three are informational — they show on the card but don't disqualify.

The digest also **mines the descriptions** for Waldo's and Muddy Paws — phrases
like "great with kids," "loves other dogs," "should be the only dog," "needs a
quiet home." Their write-ups are detailed and this recovers a lot of what the
structured fields don't carry. A negative statement always overrides a positive
one, so "not good with other dogs" wins over an earlier "loves to play."

---

## Running it yourself

```bash
pip install -r requirements.txt
python digest.py --dry-run     # build, write docs/, send nothing, touch nothing
python digest.py               # the real thing
python digest.py --reset       # re-baseline (marks everything as seen)
```

`--dry-run` still writes `docs/index.html`, so you can open it locally to check a
change before it goes out.

## The five feeds

```
GET  mpr-public-api.uk.r.appspot.com/dogs                            Muddy Paws
GET  shelterluv.com/api/v3/available-animals/3447?species=Dog        Hearts & Bones
GET  petstablished.com/api/v2/public/search/shelter_show/1512552     Waldo's
POST psl.petfinder.com/graphql                                       Labs4rescue (CT178)
POST psl.petfinder.com/graphql                                       ACC Manhattan (NY12)
```

ACC's own site is a Flutter app with no reachable feed, and their listings route
through Adopets — the Petfinder path is both easier and richer, since it carries
the full description text.

Shelterluv, Petstablished and Petfinder are all multi-tenant — adding a rescue is
one line in `SOURCES` at the bottom of `sources.py`, given its org id. ACC
Manhattan is `NY12`, Animal Haven `NY17`, NYC Second Chance `NY949`, Best Friends
SoHo `NY1183`, all through the Petfinder path.

**Quirks the code already handles**, so you don't rediscover them:

- Shelterluv returns `photos` as an object keyed by number, not an array, and
  `age_group` as an object
- Petstablished `public_url` is relative, and some images are `.HEIC` — browsers
  won't render those, so they're filtered out
- Petfinder needs `organization_id` (not `organization`), requires a `sort`
  argument, returns `null` for every image URL (build them from `_media` ids plus
  the CDN base), and reports a global `totalCount` rather than a filtered one
- **Petfinder needs `adoption_status: ["adoptable"]` or it returns the org's whole
  history.** Without it Labs4rescue came back with 600 dogs, all but 11 already
  adopted — and ACC with 100 instead of 88. This is the single easiest way to get
  a digest full of dogs that went home months ago
- Muddy Paws' site shows 71 dogs: 65 `Available` plus 6 `Waitlist Full / Pending
  Adoption`. Both are kept so nothing silently disappears; the waitlisted ones get
  a **Waitlist full** chip and are held out of Top dogs, since you can't act on them
- If a source throws, the run continues with the others; if *all* of them fail,
  it aborts without touching `seen.json` so a bad morning can't wipe your baseline
