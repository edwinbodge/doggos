#!/usr/bin/env python3
"""Daily rescue-dog digest for Edwin & Elizabeth.

  python digest.py            # build, write docs/, send if configured
  python digest.py --dry-run  # build and write, don't send, don't save state
  python digest.py --reset    # rebuild the baseline (marks everything as seen)

Environment:
  MAIL_TO           comma-separated recipients            (required to send)
  MAIL_FROM         from address                          (required to send)
  SITE_URL          public URL of the gallery page        (optional but nice)

  # pick ONE transport
  SMTP_USER / SMTP_PASSWORD           any SMTP host; SMTP_HOST + SMTP_PORT
                                      default to Gmail's (smtp.gmail.com:465).
                                      GMAIL_USER / GMAIL_APP_PASSWORD also work
  RESEND_API_KEY                      Resend — needs a verified sending domain
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import random
import smtplib
import sys
from email.message import EmailMessage

import requests

from sources import (SOURCES, Dog, LABELS, DISQUALIFIERS, INFORMATIONAL,
                     GOOD_KIDS, GOOD_DOGS, HOUSETRAINED, CRATE, FOSTER_TO_ADOPT)

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / "seen.json"
DOCS = ROOT / "docs"                     # GitHub Pages serves this folder

# ---- Top Dogs / Top Labs criteria -----------------------------------------
MAX_WEIGHT_LB = 60
MAX_AGE_YEARS = 5.0
PUPPY_YEARS = 1.0        # under this, a small dog still has growing to do
OK_BUCKETS = {"medium"}  # used when a source gives no number
NEW_WINDOW_DAYS = 7

ACCENT = "#2C6A4B"
INK = "#1B1E19"
INK_2 = "#4A5147"
MUTED = "#767D71"
LINE = "#DFDDD3"
WARN = "#A34A18"
GOLD = "#8A6A1F"

# ---- type: two families, five roles ---------------------------------------
# Web fonts don't load reliably in mail clients, so these are the durable
# equivalents of the site's Newsreader + IBM Plex Sans.
SERIF = "Georgia,'Times New Roman',serif"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

T_DISPLAY = f"600 27px/1.15 {SERIF}"     # the one headline
T_TITLE = f"600 18px/1.25 {SERIF}"       # a dog's name
T_BODY = f"400 14px/1.5 {SANS}"          # breed, prose
T_LABEL = f"500 13px/1.4 {SANS}"         # facts, buttons
T_MICRO = f"500 11px/1 {SANS}"           # chips, eyebrow, section heads


# ---------------------------------------------------------------- selection

def is_puppy(d: Dog) -> bool:
    if d.age_years is not None:
        return d.age_years < PUPPY_YEARS
    return (d.age or "").strip().lower() in {"baby", "puppy"}


def in_size_range(d: Dog) -> bool:
    """Under the weight cap — but a small dog under a year still counts,
    since a 24 lb six-month-old has plenty of growing left to do."""
    if d.weight_lb is not None:
        return d.weight_lb <= MAX_WEIGHT_LB
    bucket = (d.size_bucket or d.weight_note or "").strip().lower()
    if any(bucket.startswith(b) for b in OK_BUCKETS):
        return True
    return bucket.startswith("small") and is_puppy(d)


def in_age_range(d: Dog) -> bool:
    if d.age_years is not None:
        return d.age_years <= MAX_AGE_YEARS
    # Petfinder gives a band, not a number
    return (d.age or "").strip().lower() in {"young", "adult", "baby", "puppy"}


def top_picks(dogs: list[Dog]) -> list[Dog]:
    """Size + age hard filter, drop known disqualifiers, then rank.

    Only Hearts & Bones publishes good-with-kids/dogs as data, so requiring
    both outright would hide three of the four rescues. Instead: exclude
    anything with a known problem, and sort confirmed-good to the top.
    """
    pool = [d for d in dogs
            if in_size_range(d) and in_age_range(d) and not d.disqualified]
    # Shuffle within tiers, seeded by the date, so the order differs each day
    # but stays put if you reload — otherwise the same dogs live at the top
    # forever and the ones below never get looked at.
    rng = random.Random(dt.date.today().isoformat())
    rng.shuffle(pool)
    pool.sort(key=lambda d: (
        not d.confirmed_family_safe,                 # confirmed first
        not (GOOD_KIDS in d.traits or GOOD_DOGS in d.traits),
    ))
    return pool


# ---------------------------------------------------------------- formatting

def age_display(d: Dog) -> str:
    """One shape for age everywhere: '3.1 yr', '7 mo', or the source's band."""
    y = d.age_years
    if y is None:
        return (d.age or "").strip()
    if y < 1:
        return f"{round(y * 12)} mo"
    return f"{y:g} yr"


def sex_display(d: Dog) -> str:
    s = (d.sex or "").strip().lower()
    return {"male": "Male", "female": "Female", "m": "Male", "f": "Female"}.get(s, "")


def listed_display(d: Dog, first_seen: dict[str, str] | None) -> str:
    """How long this dog has been up.

    Only Shelterluv publishes a real intake date. For everyone else the best we
    have is when this digest first saw them, which is a floor, not the truth —
    so those read '30d+' rather than '30d'.
    """
    exact, iso = True, d.listed_on
    if not iso:
        exact, iso = False, (first_seen or {}).get(d.key, "")
    if not iso:
        return ""
    try:
        days = (dt.date.today() - dt.date.fromisoformat(iso)).days
    except ValueError:
        return ""
    if days < 0:
        return ""
    if days == 0:
        # Every genuinely new dog hits this branch on the morning it shows up,
        # so it's the most-seen label in the whole digest. "Listed 0d+" is not
        # what a person would say.
        return "Listed today"
    unit = f"{days}d" if days < 60 else f"{round(days / 30.44)}mo"
    return f"Listed {unit}" if exact else f"Listed {unit}+"


def meta_line(d: Dog, first_seen: dict[str, str] | None = None) -> str:
    parts = [d.weight_display, age_display(d), sex_display(d),
             listed_display(d, first_seen)]
    return "  ·  ".join(x for x in parts if x)


# ---------------------------------------------------------------- rendering

def chip(text: str, kind: str = "ok") -> str:
    bg, fg = {"ok": ("#EFEEE7", "#4A5147"),
              "good": ("#E6F0E9", ACCENT),
              "warn": ("#F7E9E0", WARN),
              "flex": ("#F4EDDA", GOLD)}[kind]
    return (f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'font:{T_MICRO};padding:5px 7px;border-radius:3px;'
            f'margin:0 4px 4px 0;">{html.escape(text)}</span>')


def chips_for(d: Dog) -> str:
    out = []
    for t in (GOOD_KIDS, GOOD_DOGS):
        if t in d.traits:
            out.append(chip(LABELS[t], "good"))
    for t in (HOUSETRAINED, CRATE):
        if t in d.traits:
            out.append(chip(LABELS[t]))
    if FOSTER_TO_ADOPT in d.traits:
        out.append(chip(LABELS[FOSTER_TO_ADOPT], "flex"))
    for t in sorted(d.traits & DISQUALIFIERS):
        out.append(chip(LABELS[t], "warn"))
    for t in sorted(d.traits & INFORMATIONAL):
        out.append(chip(LABELS[t]))
    if not (d.traits - {FOSTER_TO_ADOPT}):
        out.append(chip("traits not listed", "ok"))
    return "".join(out)


def dog_row(d: Dog, first_seen: dict[str, str] | None = None) -> str:
    """One dog as an email-safe table row."""
    meta = meta_line(d, first_seen)
    img = (f'<img src="{html.escape(d.photo)}" width="132" height="99" alt="{html.escape(d.name)}"'
           f' style="display:block;border-radius:5px;object-fit:cover;'
           f'width:132px;height:99px;border:1px solid {LINE};">') if d.photo else ""
    return f"""
  <tr>
    <td width="132" valign="top" style="padding:0 14px 22px 0;">
      <a href="{html.escape(d.url)}" style="text-decoration:none;">{img}</a>
    </td>
    <td valign="top" style="padding:0 0 22px 0;">
      <a href="{html.escape(d.url)}" style="font:{T_TITLE};color:{INK};
         text-decoration:none;">{html.escape(d.name)}</a>
      <span style="font:{T_MICRO};color:{MUTED};letter-spacing:.09em;
        text-transform:uppercase;">&nbsp;&nbsp;{html.escape(d.source)}</span>
      <div style="font:{T_LABEL};color:{INK_2};margin:6px 0 3px;">{html.escape(meta)}</div>
      <div style="font:{T_BODY};color:{MUTED};margin-bottom:8px;">
        {html.escape(d.breed_display)}</div>
      <div>{chips_for(d)}</div>
    </td>
  </tr>"""


def section(title: str, note: str, dogs: list[Dog], empty: str,
            first_seen: dict[str, str] | None = None) -> str:
    body = ("".join(dog_row(d, first_seen) for d in dogs) if dogs else
            f'<tr><td style="font:{T_BODY};color:{MUTED};'
            f'padding-bottom:22px;">{html.escape(empty)}</td></tr>')
    return f"""
  <tr><td style="padding:26px 0 12px;border-top:1px solid {LINE};">
    <div style="font:{T_MICRO};color:{MUTED};letter-spacing:.13em;
      text-transform:uppercase;">{html.escape(title)}</div>
    {f'<div style="font:{T_BODY};color:{MUTED};margin-top:6px;max-width:52ch;">{html.escape(note)}</div>' if note else ''}
  </td></tr>
  <tr><td><table role="presentation" cellpadding="0" cellspacing="0" border="0"
    width="100%">{body}</table></td></tr>"""


def build_email(new: list[Dog], picks: list[Dog], labs: list[Dog],
                total: int, site: str,
                first_seen: dict[str, str] | None = None) -> str:
    today = dt.datetime.now().strftime("%A %-d %B")
    link = (f'<a href="{html.escape(site)}" style="display:inline-block;background:{ACCENT};'
            f'color:#fff;font:{T_LABEL};padding:12px 18px;border-radius:4px;'
            f'text-decoration:none;">Browse all {total} dogs with photos →</a>'
            ) if site else (
            f'<span style="font:{T_BODY};color:{MUTED};">'
            f'Set SITE_URL to link the full gallery here.</span>')

    cta_top = (f'<a href="{html.escape(site)}" style="display:inline-block;background:{ACCENT};'
               f'color:#fff;font:{T_LABEL};padding:11px 16px;border-radius:4px;'
               f'text-decoration:none;">Browse all {total} dogs →</a>') if site else ""

    return f"""<!doctype html><html><body style="margin:0;background:#F6F5F0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
  style="background:#F6F5F0;padding:26px 14px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
  style="max-width:600px;background:#fff;border:1px solid {LINE};border-radius:6px;
  padding:26px 24px;">

  <tr><td style="padding-bottom:6px;">
    <div style="font:{T_MICRO};color:{MUTED};
      letter-spacing:.14em;text-transform:uppercase;">{today}</div>
    <div style="font:{T_DISPLAY};color:{INK};margin:8px 0 16px;">
      {len(new)} new doggo{'' if len(new)==1 else 's'} for you</div>
    {cta_top}
  </td></tr>

  {section("New today", "", new, "No new listings since yesterday.", first_seen)}
  {section("Top dogs", "", picks[:12], "Nothing matched today.", first_seen)}
  {section("Top labs", "", labs[:8], "No Labs matched today.", first_seen)}

  <tr><td style="padding:22px 0 6px;border-top:1px solid {LINE};">{link}</td></tr>

</table></td></tr></table></body></html>"""


# ---------------------------------------------------------------- gallery page

def build_page(dogs: list[Dog], new_keys: set[str],
               first_seen: dict[str, str] | None = None) -> str:
    payload = [{
        "s": d.source, "n": d.name, "u": d.url, "b": d.breed_display,
        "f": [x for x in [d.weight_display, age_display(d), sex_display(d)] if x],
        "listed": listed_display(d, first_seen),
        "p": d.photos,
        "g": [LABELS[t] for t in (GOOD_KIDS, GOOD_DOGS, HOUSETRAINED, CRATE,
                                  FOSTER_TO_ADOPT) if t in d.traits],
        "w": [LABELS[t] for t in sorted(d.traits & DISQUALIFIERS)],
        "i": sorted(LABELS[t] for t in d.traits & INFORMATIONAL),
        "new": d.key in new_keys,
        "lab": d.is_lab,
        "seen": (first_seen or {}).get(d.key, ""),
        "lb": d.weight_lb,
        "yr": d.age_years,
        "sex": d.sex,
        "bucket": d.size_bucket or d.weight_note or "",
    } for d in dogs]
    tpl = (ROOT / "page_template.html").read_text()
    # This lands inside a <script> block, and the text comes from the rescues,
    # not from us. A description containing "</script>" would close the tag and
    # everything after it would parse as HTML. Escaping "<" (and the two line
    # separators that are legal JSON but were historically illegal in JS string
    # literals) makes the payload inert wherever it's embedded.
    blob = (json.dumps(payload, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))
    return tpl.replace("/*__DATA__*/[]", blob) \
              .replace("__NEWDAYS__", str(NEW_WINDOW_DAYS))\
              .replace("__UPDATED__", dt.datetime.now().strftime("%-d %B %Y, %-I:%M %p"))


# ---------------------------------------------------------------- delivery

def env(name: str, default: str = "") -> str:
    """os.environ.get, but an empty value counts as missing.

    Actions expands an undefined `vars.X` to "" rather than leaving the variable
    unset, so every optional env var arrives as an empty string rather than
    absent. os.environ.get's default never fires, and int("") raises.
    """
    return os.environ.get(name, "").strip() or default


def send(subject: str, html_body: str) -> str:
    to = [x.strip() for x in os.environ.get("MAIL_TO", "").split(",") if x.strip()]
    sender = os.environ.get("MAIL_FROM", "")
    if not to or not sender:
        return "not sent (MAIL_TO / MAIL_FROM unset)"

    # Any SMTP provider works. Defaults are Gmail's, so GMAIL_USER /
    # GMAIL_APP_PASSWORD alone still work; set SMTP_HOST and SMTP_PORT to point
    # somewhere else (Brevo, Fastmail, SMTP2GO) if Google won't issue you an app
    # password. Port 465 is implicit TLS, 587 is STARTTLS — both handled below.
    user = env("SMTP_USER") or env("GMAIL_USER")
    password = env("SMTP_PASSWORD") or env("GMAIL_APP_PASSWORD")
    if password:
        host = env("SMTP_HOST", "smtp.gmail.com")
        port = int(env("SMTP_PORT", "465"))
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(to)
        msg.set_content("This digest is best viewed as HTML.")
        msg.add_alternative(html_body, subtype="html")
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port) as s:
                s.starttls()
                s.login(user, password)
                s.send_message(msg)
        return f"sent via {host} to {len(to)} recipient(s)"

    if key := os.environ.get("RESEND_API_KEY"):
        r = requests.post("https://api.resend.com/emails",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"from": sender, "to": to,
                                "subject": subject, "html": html_body},
                          timeout=30)
        r.raise_for_status()
        return f"sent via Resend to {len(to)} recipient(s)"

    return "not sent (no transport configured)"


# ---------------------------------------------------------------- main

def load_first_seen() -> dict[str, str]:
    """key -> ISO date the dog first appeared. Migrates the old list format."""
    if not STATE.exists():
        return {}
    raw = json.loads(STATE.read_text())
    if isinstance(raw.get("first_seen"), dict):
        return raw["first_seen"]
    today = dt.date.today().isoformat()
    return {k: today for k in raw.get("seen", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--test", action="store_true",
                    help="send one email now and change nothing — stands in "
                         "recent dogs as 'new' so the email looks realistic")
    args = ap.parse_args()

    dogs: list[Dog] = []
    for label, fn in SOURCES:
        try:
            got = fn()
            dogs += got
            print(f"  {label:<16} {len(got):>4} dogs")
        except Exception as e:                    # one bad source ≠ dead digest
            print(f"  {label:<16} FAILED: {e}", file=sys.stderr)

    if not dogs:
        print("No dogs from any source — aborting without touching state.",
              file=sys.stderr)
        return 1

    first_seen = load_first_seen()
    first_run = not first_seen
    today = dt.date.today().isoformat()
    new = [d for d in dogs if d.key not in first_seen]
    new_keys = {d.key for d in new}
    for d in new:
        first_seen.setdefault(d.key, today)

    if args.test and not new:
        # Nothing is genuinely new, which would make the test email a header and
        # two sections. Stand in the most recently first-seen dogs so the "New
        # today" section shows what a normal morning looks like. State is left
        # untouched below, so these stay eligible to be announced for real.
        recent = sorted(dogs, key=lambda d: first_seen.get(d.key, ""),
                        reverse=True)
        new = recent[:8]
        new_keys = {d.key for d in new}
        print(f"  [test] standing in {len(new)} recent dogs as new")

    picks = top_picks(dogs)
    labs = [d for d in picks if d.source == "Labs4rescue"]
    picks_non_lab = [d for d in picks if d.source != "Labs4rescue"]

    DOCS.mkdir(exist_ok=True)
    # Without this, GitHub Pages runs the folder through Jekyll, which builds
    # nothing useful here and drops any file starting with "_" or ".". The page
    # is self-contained, so opt out. Written every run so a fresh clone or a
    # deleted docs/ can't lose it.
    (DOCS / ".nojekyll").write_text("")
    (DOCS / "index.html").write_text(build_page(dogs, new_keys, first_seen))
    print(f"  wrote {DOCS/'index.html'} ({len(dogs)} dogs)")

    if first_run and not args.reset and not args.test:
        print(f"Baseline recorded ({len(dogs)} dogs). No email on the first run.")
    elif args.reset:
        print(f"Baseline reset to {len(dogs)} dogs.")
    else:
        subject = f"{len(new)} new doggo{'' if len(new)==1 else 's'} for you"
        body = build_email(new, picks_non_lab, labs, len(dogs),
                           os.environ.get("SITE_URL", ""), first_seen)
        (DOCS / "latest-email.html").write_text(body)
        if args.dry_run:
            print(f"[dry run] would send: {subject}")
        else:
            print(f"  {send(subject, body)}")
        print(f"  new: {len(new)} | top dogs: {len(picks_non_lab)} | top labs: {len(labs)}")

    if not args.dry_run and not args.test:
        for d in dogs:
            first_seen.setdefault(d.key, today)
        STATE.write_text(json.dumps(
            {"updated": dt.datetime.now().isoformat(timespec="seconds"),
             "first_seen": dict(sorted(first_seen.items()))}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
