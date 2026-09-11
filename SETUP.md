# Setting this up, start to finish

Three things to do, in this order. Budget about 30 minutes.

1. Make a Gmail account for your agents
2. Put the code on GitHub and turn on Pages
3. Read the security notes before you push anything

---

# 1. The agent Gmail account

You said you didn't want to give this thing raw access to your personal email.
That instinct is right, and here's the specific reason: **an app password is not
scoped.** Google doesn't let you say "this password may only send mail." It grants
full IMAP/SMTP access to that mailbox — read, send, delete. There is no way to
narrow it. So the password itself is the security boundary, and the only real
control you have is *which mailbox it opens.* Make that mailbox one that contains
nothing.

### Create it

1. Sign out, or open a private window, and go to
   [accounts.google.com/signup](https://accounts.google.com/signup)
2. Pick something you'll recognize in a `From:` line — `edwin.doggobot@gmail.com`,
   `bodgee.agents@gmail.com`, whatever. It shows up in your inbox every morning
3. Google will want a phone number to verify. Yours is fine — that's for account
   recovery, not for the script
4. **Set the recovery email to your personal address.** If you ever lose this
   account you want a way back in
5. Use a password from your password manager. Long, random, stored there, never
   typed into anything else

### Turn on 2-Step Verification

App passwords don't exist until 2FA is on — Google hides the page otherwise.

**[myaccount.google.com/security](https://myaccount.google.com/security) → 2-Step
Verification → turn on.** Authenticator app or SMS, either works.

### Create the app password

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Name it `doggos` — the name is only a label so you can revoke the right one later
3. You get 16 characters in four groups. **Copy it now**, Google won't show it twice
4. Paste it straight into the GitHub secret in step 2 below. Don't put it in a
   file, a note, or a chat message. If you lose it, delete it on that page and
   make a new one — takes ten seconds

If it ever leaks, that same page has a **Revoke** button, and revoking is
instant. That's the whole reason a throwaway account is worth the ten minutes:
the worst case is "someone can send mail as doggobot and read three months of
adoption listings," and you kill it with one click.

### While you're in there

Send yourself a test later, then **turn off** anything you don't need on that
account: no Drive sync, no Photos backup, don't sign a browser into it. It's a
mail relay, not an identity.

---

# 2. GitHub

### Create the repo

```bash
cd doggos                      # the unzipped folder
git init
git add .
git commit -m "doggo digest"
```

Then either use the GitHub CLI:

```bash
gh repo create doggos --public --source=. --push
```

or make an empty repo at [github.com/new](https://github.com/new) (named `doggos`,
**Public**, no README/gitignore/license — you have those) and:

```bash
git remote add origin https://github.com/<you>/doggos.git
git branch -M main
git push -u origin main
```

**Why public:** GitHub Pages is free on public repos only; on a private repo it
needs a paid plan. Nothing in this repo is sensitive — it's Python that reads
public adoption listings. Your email addresses and the app password go in
**Secrets**, which are not part of the repo and stay private even though the code
is public. More on that below.

### Turn on Pages

**Settings → Pages → Build and deployment → Source: Deploy from a branch →
Branch: `main`, folder: `/docs` → Save.**

Your site lands at `https://<you>.github.io/doggos/`. It'll 404 until the first
real run writes `docs/index.html` — that's expected, not a mistake.

### Add the secrets

**Settings → Secrets and variables → Actions → Secrets tab → New repository secret.**
Four of them:

| Name | Value |
|---|---|
| `MAIL_TO` | `you@gmail.com,elizabeth@gmail.com` — comma-separated, no spaces |
| `MAIL_FROM` | the new agent address |
| `GMAIL_USER` | the same new agent address |
| `GMAIL_APP_PASSWORD` | the 16 characters, spaces stripped |

Then the **Variables** tab (not Secrets — it's just a URL and it's nice to be able
to read it back):

| Name | Value |
|---|---|
| `SITE_URL` | `https://<you>.github.io/doggos/` — with the trailing slash |

`MAIL_TO` goes in Secrets rather than Variables on purpose: it keeps your and
Elizabeth's real addresses out of a public repo and out of the build logs.

### Prime the baseline

**Actions → Daily doggo digest → Run workflow → Run workflow.**

**This first run sends no email, by design.** It records today's ~237 dogs as the
baseline. Without it, tomorrow's "new doggos" email would be 237 dogs long. It
does publish the site, so once it's green, open `https://<you>.github.io/doggos/`
and the directory should be there.

If Actions says workflows are disabled on a fresh fork/repo, there's a green
"I understand my workflows, go ahead and enable them" button on the Actions tab.

### Then let it run

11:23 UTC daily — 7:23am Eastern in summer, 6:23am in winter. GitHub's cron
doesn't know about daylight saving, so the clock-time shifts twice a year while
the schedule stays put. Change the `cron:` line in `.github/workflows/daily.yml`
if the hour drifts somewhere you don't want it.

**Don't expect it to the minute.** Scheduled workflows run on shared capacity and
GitHub makes no delivery guarantee — a run set for `0 11` once fired at 14:40
UTC, 3h40m late. The minute here is deliberately `:23` rather than `:00`, since
`0` is the most common minute in everyone's cron and jobs there queue behind the
crowd. Off-peak minutes cut the wait a lot; they don't eliminate it. If you ever
need a guaranteed time, drive it from an external scheduler that calls the
`workflow_dispatch` API instead.

### Checking on it

- **Actions tab** shows every run, green or red. Click one to read the log
- GitHub emails you when a scheduled workflow fails, so you'll know
- GitHub **disables cron workflows after 60 days of no repo activity** on public
  repos. This one commits `seen.json` every day it finds a change, which counts as
  activity — so it keeps itself alive. But if you see it go quiet for a couple of
  months, that's the reason; hit Run workflow and it resumes
- Free tier gives 2,000 Actions minutes/month. This run takes about a minute.
  You'll use ~30

### Changing something later

```bash
git pull                       # the bot commits daily, so pull before you edit
# edit
git add -A && git commit -m "tweak" && git push
```

To preview before pushing:

```bash
pip install -r requirements.txt
python digest.py --dry-run     # builds docs/index.html, sends nothing, saves nothing
open docs/index.html
```

`--reset` re-baselines if you ever want to start the "new" tracking over.

---

# 3. Security — what actually matters here

Ordered by how much it would hurt.

### The app password is the only real secret

Everything else in this project is public information. Treat those 16 characters
the way you'd treat a house key:

- **Never in a file.** Not `.env`, not a config, not a comment, not a commit "just
  to test." Git remembers deleted content forever — a password committed once and
  removed in the next commit is still sitting in the repo's history, and on a
  public repo, scanner bots find those within minutes. If you ever do it by
  accident, don't try to rewrite history; **revoke the password on Google and make
  a new one.** That's the fix, and it takes less time than the cleanup
- **Only in GitHub Secrets.** Encrypted at rest, injected as an environment
  variable at run time, and GitHub masks them in logs — if the script ever printed
  it, the log shows `***`. Masking is a safety net, not a guarantee (it can miss
  a value that's been transformed or base64'd), so the script never prints it
- Once saved, GitHub won't show it back to you. That's correct behavior. To change
  it you overwrite it

### The site is fully public

Anyone with the URL can read `https://<you>.github.io/doggos/`, and there's no way
to password-protect a Pages site on the free tier. It's not linked from anywhere
and the URL isn't guessable, but treat it as public, because it is. Practically:

- **Don't put anything personal on that page.** It's dog listings and photo URLs
  from the rescues. Keep it that way. No notes to yourself about which application
  you sent, no addresses, no phone numbers
- Your **hidden-dogs list never leaves the browser.** It's in `localStorage`, on
  your device, not in the repo and not on the server. That's also why you and
  Elizabeth keep separate lists — and why clearing site data resets it
- The email itself is the private part. It goes to two addresses over SMTP and
  isn't published anywhere

### Workflow permissions

`.github/workflows/daily.yml` declares:

```yaml
permissions:
  contents: write
```

That's deliberate and it's the whole grant — enough to commit `seen.json` and
`docs/`, and nothing else. Without that block the job would inherit whatever the
repo default is, which on older repos is write access to issues, packages,
deployments and more. If you ever add a step to this workflow, don't loosen it.

Related: **Settings → Actions → General → Workflow permissions** should read "Read
repository contents and packages permissions" as the default. The per-workflow
block above overrides it upward where needed, which is the right direction.

### Pinning actions

The workflow uses `actions/checkout@v4` and `actions/setup-python@v5` — both
GitHub's own, and `@v4` is a moving tag. That's the normal trade-off: you get
security patches automatically, and you're trusting GitHub not to ship something
malicious under their own tag. Fine here. If you ever add a **third-party**
action, pin it to a full commit SHA (`uses: someone/thing@a1b2c3d…`) instead of a
tag — a tag can be repointed by whoever owns the repo, a SHA can't.

### The data you're pulling in

The script fetches JSON from five rescue APIs and renders names, breeds and
descriptions into HTML. That's untrusted input in the strict sense — if a rescue's
listing contained `<script>`, you don't want it running on your page. Two things
already cover this: the values go through `html.escape()` before they're
interpolated, and Pages serves your site on `github.io`, a separate origin from
anything you care about. The photo URLs are rendered as `<img src>` pointed at the
rescues' own CDNs, which is exactly what a browser does safely.

If you add a source later, escape its output the same way. That's the one rule.

### Dependencies

`requirements.txt` is one line: `requests`. A small dependency tree is a real
security property — every package you add is code running with access to your
secrets in that job. Keep it small. Turn on **Settings → Code security →
Dependabot alerts** and it'll tell you if `requests` ever needs patching.

Also worth flipping on while you're there: **Secret scanning** and **Push
protection**. Push protection blocks a commit containing something that looks like
a credential *before* it reaches GitHub — the single most useful safety net for the
mistake you're most likely to make.

### Things you don't need to worry about

- The five rescue APIs are unauthenticated public endpoints — the same ones their
  own websites call. No keys, no accounts, no terms you're breaking by reading them
- The script only reads. It never submits an application or contacts a rescue
- If a source fails, the run continues with the other four; if *all five* fail, it
  aborts without touching `seen.json`, so a bad morning can't wipe your baseline
  and make tomorrow's email 237 dogs long

### If something goes wrong

| Symptom | Cause |
|---|---|
| No email, workflow green | Check the Actions log — if nothing was new, nothing sends. That's correct |
| `SMTPAuthenticationError` | App password wrong, has spaces in it, or 2FA got turned off on that account |
| Site 404s | Pages source isn't `main` / `/docs`, or the first run hasn't committed `docs/` yet |
| Email arrives, links dead | `SITE_URL` variable is missing or has no trailing slash |
| First email had 237 dogs | The priming run got skipped. `python digest.py --reset` locally, commit `seen.json` |
