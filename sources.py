"""Fetchers for the four rescue feeds, normalised to one Dog record.

None of these need an API key. Notes on each source's quirks live next to
the code that works around them.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass, field

import requests

TIMEOUT = 30
UA = {"User-Agent": "personal-adoption-digest/2.0 (individual adopter)"}

# Traits we care about, normalised across sources.
GOOD_KIDS, GOOD_DOGS = "good_with_kids", "good_with_dogs"
HOUSETRAINED, CRATE = "housetrained", "crate_trained"
FOSTER_TO_ADOPT = "foster_to_adopt"

# Disqualifiers — any of these knocks a dog out of Top Dogs.
NO_KIDS, NO_DOGS = "not_good_with_kids", "not_good_with_dogs"
SOLO_ONLY, QUIET_ONLY = "solo_dog", "quiet_home"
STAFF_ONLY, BONDED = "staff_handling", "bonded_pair"

# Informational — worth surfacing, but not a reason to drop a dog.
SLOW_WARM, MEDICAL, GUARDING = "slow_to_warm", "medical_needs", "resource_guarding"
LONG_STAY = "long_stay"

# Listed but not actually gettable right now.
WAITLIST = "waitlist_full"

DISQUALIFIERS = {NO_KIDS, NO_DOGS, SOLO_ONLY, QUIET_ONLY, STAFF_ONLY, BONDED, WAITLIST}
INFORMATIONAL = {SLOW_WARM, MEDICAL, GUARDING, LONG_STAY}

LABELS = {
    GOOD_KIDS: "Good with kids", GOOD_DOGS: "Good with dogs",
    HOUSETRAINED: "Housetrained", CRATE: "Crate-trained",
    FOSTER_TO_ADOPT: "Foster-to-adopt",
    NO_KIDS: "Adult home preferred", NO_DOGS: "Not good with dogs",
    SOLO_ONLY: "Solo dog only", QUIET_ONLY: "Needs a quiet home",
    STAFF_ONLY: "Staff handling only", BONDED: "Bonded pair",
    SLOW_WARM: "Slow to warm up", MEDICAL: "Has medical needs",
    GUARDING: "Guards food or toys", LONG_STAY: "Long stay",
    WAITLIST: "Waitlist full",
}


@dataclass
class Dog:
    source: str
    uid: str
    name: str
    url: str
    age: str = ""
    age_years: float | None = None
    weight_lb: float | None = None
    weight_note: str = ""          # bucket text when there's no number
    size_bucket: str = ""          # Small / Medium / Large when given
    sex: str = ""
    breed: str = ""
    photos: list[str] = field(default_factory=list)
    description: str = ""
    traits: set[str] = field(default_factory=set)
    raw_tags: list[str] = field(default_factory=list)   # source's own wording
    listed_on: str = ""            # ISO date the RESCUE says it was listed
                                   # (only Shelterluv publishes one)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.uid}"

    @property
    def photo(self) -> str:
        return self.photos[0] if self.photos else ""

    @property
    def weight_display(self) -> str:
        """Whole pounds — sources report things like 40.3125."""
        if self.weight_lb:
            return f"{round(self.weight_lb):g} lb"
        bucket = self.weight_note or self.size_bucket
        return bucket or "size n/a"

    @property
    def breed_display(self) -> str:
        b = (self.breed or "").strip()
        if not b or b.lower() in {"unknown", "unknown mix", "unknown breed", "-", "n/a"}:
            return "Unknown breed"
        return b

    @property
    def is_lab(self) -> bool:
        return bool(re.search(r"\blab(rador)?\b|retriever", self.breed, re.I))

    @property
    def confirmed_family_safe(self) -> bool:
        return GOOD_KIDS in self.traits and GOOD_DOGS in self.traits

    @property
    def disqualified(self) -> bool:
        return bool(self.traits & DISQUALIFIERS)


# --------------------------------------------------------------- helpers

def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def years_from_text(s: str) -> float | None:
    if not s:
        return None
    if m := re.search(r"(\d+(?:\.\d+)?)\s*year", s, re.I):
        return float(m.group(1))
    if m := re.search(r"(\d+(?:\.\d+)?)\s*month", s, re.I):
        return float(m.group(1)) / 12
    return None


def years_since(when) -> float | None:
    """Age from a birthday, accepting the three shapes these feeds use:
    an ISO string (Petstablished), a unix int, and a unix timestamp that
    Shelterluv hands back as a *string* of digits.
    """
    if when in (None, ""):
        return None
    try:
        if isinstance(when, str) and not re.fullmatch(r"-?\d+", when.strip()):
            born = dt.datetime.fromisoformat(when)
            now = dt.datetime.now(born.tzinfo)
        else:
            born = dt.datetime.fromtimestamp(int(when), dt.timezone.utc)
            now = dt.datetime.now(dt.timezone.utc)
        return round((now - born).days / 365.25, 1)
    except Exception:
        return None


# Muddy Paws and Waldo's publish no structured traits, but their write-ups are
# rich. These patterns recover the signal that would otherwise be invisible.
_TEXT_TRAITS: list[tuple[str, str]] = [
    (GOOD_KIDS, r"good with (kids|children)|great with (kids|children)|"
                r"loves (kids|children)|kid-friendly|child-friendly"),
    (GOOD_DOGS, r"good with (other )?dogs|great with (other )?dogs|"
                r"loves (other )?dogs|gets along (well )?with (other )?dogs|"
                r"dog-friendly|plays well with"),
    (HOUSETRAINED, r"house ?-?trained|potty ?-?trained|fully housebroken"),
    (CRATE, r"crate ?-?trained"),
    (NO_KIDS, r"no (small )?(kids|children)|adult(s)? only home|"
              r"without (kids|children)|not good with (kids|children)"),
    (NO_DOGS, r"not good with (other )?dogs|no other dogs|dog[- ]selective|"
              r"only dog|sole dog|reactive (to|toward) (other )?dogs"),
    (QUIET_ONLY, r"quiet (home|environment|neighborhood|household)|"
                 r"calm (home|environment)|away from the (hustle|city)"),

    # ACC writes in a house style — these sentences recur almost verbatim
    (GOOD_KIDS, r"lived with (children|kids) in my previous home"),
    (GOOD_DOGS, r"lived with dogs in my previous home|playgroup rockstar|"
                r"does well in playgroup"),
    (NO_KIDS,   r"only adult humans|without very tiny humans|adult[- ]only|"
                r"no children under|no kids under"),
    (NO_DOGS,   r"no other dogs|without other dogs|only pet in the home"),
    (SLOW_WARM, r"slow introductions|slow to adjust|at my own pace|"
                r"on my own terms|call the shots|slow to warm"),
    (MEDICAL,   r"medical needs that staff|i have medical needs"),
    (GUARDING,  r"don'?t always like to share (my )?(food|toys)|resource guard"),
    (LONG_STAY, r"long ?-?stay|longest resident|waiting patiently for|been (here|with us) (for )?(over|more than)"),
]


def traits_from_text(text: str) -> set[str]:
    """Best-effort trait extraction from a free-text description."""
    t = (text or "").lower()
    found = set()
    for trait, pattern in _TEXT_TRAITS:
        if re.search(pattern, t):
            found.add(trait)
    # a negative statement always beats the positive one
    if NO_DOGS in found:
        found.discard(GOOD_DOGS)
    if NO_KIDS in found:
        found.discard(GOOD_KIDS)
    return found


# --------------------------------------------------------------- Muddy Paws

MP_API = "https://mpr-public-api.uk.r.appspot.com/dogs"

# Their vocabulary is exception-based: they publish warnings, never positives.
_MP_TRAITS = [
    (r"adult home preferred", NO_KIDS),
    (r"solo dog", SOLO_ONLY),
    (r"quiet neighborhood", QUIET_ONLY),
    (r"staff handling", STAFF_ONLY),
    (r"bonded pair", BONDED),
    (r"flex adoption", FOSTER_TO_ADOPT),
]


def fetch_muddy_paws() -> list[Dog]:
    data = requests.get(MP_API, headers=UA, timeout=TIMEOUT).json()
    out = []
    for d in data:
        # Their site shows 71: 65 "Available" plus 6 on a full waitlist. Keep
        # both so nothing silently disappears, and flag the waitlisted ones.
        status = d.get("Status") or ""
        if not d.get("ShowOnWebsite") or status not in {
                "Available", "Waitlist Full / Pending Adoption"}:
            continue
        tags = [clean(a) for a in (d.get("Attributes") or [])]
        traits = set()
        for pattern, trait in _MP_TRAITS:
            if any(re.search(pattern, t, re.I) for t in tags):
                traits.add(trait)
        desc = clean(d.get("Description", ""))
        traits |= traits_from_text(desc)
        if status != "Available":
            traits.add(WAITLIST)

        out.append(Dog(
            source="Muddy Paws", uid=str(d.get("Animal_ID")),
            name=d.get("Name", "?"),
            url=f"https://www.muddypawsrescue.org/adoptable?dog={d.get('Animal_ID')}",
            age=d.get("Age", ""), age_years=years_from_text(d.get("Age", "")),
            weight_lb=d.get("CurrentWeightPounds"),
            sex=d.get("Sex", ""), breed=d.get("Breed") or "Unknown mix",
            photos=[u for u in ([d.get("CoverPhoto")] + (d.get("Photos") or []))
                    if isinstance(u, str)][:10],
            description=desc[:600], traits=traits, raw_tags=tags,
        ))
    return _dedupe_photos(out)


# --------------------------------------------------------------- Shelterluv

# The only source that publishes positive traits as data.
_SL_TRAITS = [
    (r"good with kids|good with children", GOOD_KIDS),
    (r"good with dogs", GOOD_DOGS),
    (r"not good with (kids|children)", NO_KIDS),
    (r"not good with dogs", NO_DOGS),
    (r"house ?trained", HOUSETRAINED),
    (r"crate ?-?trained", CRATE),
    (r"trial period", FOSTER_TO_ADOPT),
    (r"prefers quiet|outside the city", QUIET_ONLY),
]


def _iso_from_unix(ts) -> str:
    try:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date().isoformat()
    except Exception:
        return ""


def _sl_photos(photos) -> list[str]:
    """Shelterluv returns photos as an object keyed by index, not a list."""
    if not isinstance(photos, dict):
        return []
    vals = [p for p in photos.values() if isinstance(p, dict) and p.get("url")]
    vals.sort(key=lambda p: (not p.get("isCover"), p.get("order_column") or 0))
    return [p["url"] for p in vals]


def fetch_shelterluv(org_id: str, label: str) -> list[Dog]:
    payload = requests.get(
        f"https://www.shelterluv.com/api/v3/available-animals/{org_id}",
        params={"species": "Dog"}, headers=UA, timeout=TIMEOUT).json()
    out = []
    for a in payload.get("animals", []):
        if not a.get("adoptable"):
            continue
        tags = [str(t) for t in (a.get("attributes") or [])]
        traits = set()
        for pattern, trait in _SL_TRAITS:
            if any(re.search(pattern, t, re.I) for t in tags):
                traits.add(trait)
        if NO_DOGS in traits:
            traits.discard(GOOD_DOGS)

        bucket = a.get("weight_group") or ""
        out.append(Dog(
            source=label, uid=str(a.get("uniqueId")), name=(a.get("name") or "?").strip(),
            url=a.get("public_url", ""),
            age=(a.get("age_group") or {}).get("name", ""),
            age_years=years_since(a.get("birthday")),
            weight_note=bucket,
            size_bucket=bucket.split(" ")[0] if bucket else "",
            sex=a.get("sex", ""),
            breed=" / ".join(x for x in [a.get("breed"), a.get("secondary_breed")] if x),
            photos=_sl_photos(a.get("photos"))[:10],
            traits=traits, raw_tags=tags,
            listed_on=_iso_from_unix(a.get("intake_date")),
        ))
    return out


# --------------------------------------------------------------- Petstablished

def _ps_url(p: dict) -> str:
    """public_url comes back relative."""
    u = p.get("public_url") or ""
    return ("https://petstablished.com" + u) if u.startswith("/") else (
        u or p.get("adopt_url", ""))


def fetch_petstablished(org_id: str, label: str) -> list[Dog]:
    out, page, pages = [], 1, 1
    while page <= pages and page <= 20:
        payload = requests.get(
            f"https://petstablished.com/api/v2/public/search/shelter_show/{org_id}",
            params={"sort": "default", "page": page},
            headers=UA, timeout=TIMEOUT).json()
        pages = int(payload.get("shelter_pets_total_page") or 1)

        for p in payload.get("shelter_pets", []):
            if p.get("no_longer_available"):
                continue
            lb = None
            if m := re.search(r"(\d+(?:\.\d+)?)", str(p.get("weight") or "")):
                lb = float(m.group(1))
            desc = clean(p.get("description", ""))
            traits = traits_from_text(desc)      # no structured traits at all here
            if p.get("is_bonded"):
                traits.add(BONDED)

            # images are [{thumb_url}] objects; .HEIC files won't render in a browser
            gallery = [p.get("thumb_url")] + [
                i.get("thumb_url") for i in (p.get("images") or [])
                if isinstance(i, dict)]
            gallery = [u for u in gallery if u and not u.lower().endswith(".heic")]

            out.append(Dog(
                source=label, uid=str(p.get("pet_id")), name=p.get("name", "?"),
                url=_ps_url(p), age=p.get("age", ""),
                age_years=years_since(p.get("date_of_birth")),
                weight_lb=lb, size_bucket=p.get("size") or "",
                sex=p.get("sex", ""),
                breed=" / ".join(x for x in [p.get("primary_breed"),
                                             p.get("secondary_breed")] if x),
                photos=gallery[:10], description=desc[:600], traits=traits,
            ))
        page += 1
    return _dedupe_photos(out)


# --------------------------------------------------------------- Petfinder

PF_GQL = "https://psl.petfinder.com/graphql"
PF_CDN = "https://dbw3zep4prcju.cloudfront.net/"

_PF_ORG_Q = ("query GetOrganization($organizationId: String!, $idType: String!) "
             "{ organization(id: $organizationId, idType: $idType) "
             "{ organizationName displayId organizationId } }")

_PF_SEARCH_Q = (
    "query S($pagination: PaginationInfoInput!, $filters: AnimalSearchFiltersInput!, "
    "$sort: [SortInput!]!) { searchAnimal(pagination: $pagination sort: $sort "
    "filters: $filters) { animals { animalId animalName primaryPhotoId "
    "description _media { mediaId } behavior { houseTrained } "
    "physical { sex size { label } breed { primary mixed } age { label } } "
    "publicUrl { url } } } }")


# ACC embeds the real numbers in their write-up — every one of their dogs had
# both when checked, which beats Petfinder's Small/Medium/Large bucket.
def _weight_from_text(text: str) -> float | None:
    if m := re.search(r"weight:\s*([\d.]+)\s*lb", text or "", re.I):
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _age_from_text(text: str) -> float | None:
    if m := re.search(r"age:\s*(\d+)\s*yrs?(?:\s*(\d+)\s*mths?)?", text or "", re.I):
        return round(int(m.group(1)) + int(m.group(2) or 0) / 12, 1)
    return None


def _pf_post(body: dict) -> dict:
    return requests.post(PF_GQL, json=body,
                         headers={**UA, "Content-Type": "application/json"},
                         timeout=TIMEOUT).json()


def fetch_petfinder_org(display_id: str, label: str) -> list[Dog]:
    """Petfinder's public widget GraphQL endpoint — no API key needed.

    Their REST API stopped issuing keys in 2024; this is what the embeddable
    pet-scroller widget calls and it answers unauthenticated.
    """
    org = _pf_post({"query": _PF_ORG_Q,
                    "variables": {"organizationId": display_id,
                                  "idType": "display_id"}})
    oid = ((org.get("data") or {}).get("organization") or {}).get("organizationId")
    if not oid:
        raise RuntimeError(f"Petfinder org lookup failed for {display_id}")

    out, page, seen = [], 0, set()
    while page < 10:
        res = _pf_post({"query": _PF_SEARCH_Q, "variables": {
            "isConsumer": True,
            # organization_id (not organization); sort is required; and
            # adoption_status is ESSENTIAL — without it the search returns the
            # org's entire history. Labs4rescue came back with 600 dogs, all but
            # 11 already adopted.
            "filters": {"animal_type": ["dog"], "organization_id": [oid],
                        "adoption_status": ["adoptable"]},
            "pagination": {"fromPage": page, "pageSize": 100},
            "sort": [{"field": "animal_type", "order": "desc"}]}})
        animals = (((res.get("data") or {}).get("searchAnimal") or {})
                   .get("animals") or [])
        fresh = [a for a in animals if a.get("animalId") not in seen]
        if not fresh:
            break

        for a in fresh:
            aid = a.get("animalId")
            seen.add(aid)
            phys = a.get("physical") or {}
            # mediaUrl always comes back null — build CDN paths from the ids
            gallery = [f"{PF_CDN}animal/{aid}/image/{m['mediaId']}.jpg"
                       for m in (a.get("_media") or []) if m.get("mediaId")]
            if a.get("primaryPhotoId"):
                cover = PF_CDN + a["primaryPhotoId"]
                gallery = [cover] + [g for g in gallery if g != cover]

            desc = clean(a.get("description", ""))
            traits = traits_from_text(desc)
            if str((a.get("behavior") or {}).get("houseTrained", "")).lower() == "yes":
                traits.add(HOUSETRAINED)

            lb = _weight_from_text(desc)
            yrs = _age_from_text(desc)
            bucket = (phys.get("size") or {}).get("label", "")

            path = ((a.get("publicUrl") or {}).get("url") or "").lstrip("/")
            out.append(Dog(
                source=label, uid=str(aid), name=a.get("animalName", "?"),
                url=f"https://www.petfinder.com/{path}" if path else "",
                age=(f"{yrs:g} yr" if yrs is not None
                     else (phys.get("age") or {}).get("label", "")),
                age_years=yrs,
                weight_lb=lb,
                size_bucket=bucket, weight_note="" if lb else bucket,
                sex=phys.get("sex") or "",
                breed=(phys.get("breed") or {}).get("primary") or "",
                photos=gallery[:10], description=desc[:600], traits=traits,
            ))
        page += 1
    return out


def _dedupe_photos(dogs: list[Dog]) -> list[Dog]:
    for d in dogs:
        seen, keep = set(), []
        for u in d.photos:
            if u not in seen:
                seen.add(u)
                keep.append(u)
        d.photos = keep
    return dogs


SOURCES = [
    ("Muddy Paws", fetch_muddy_paws),
    ("Hearts & Bones", lambda: fetch_shelterluv("3447", "Hearts & Bones")),
    ("Waldo's", lambda: fetch_petstablished("1512552", "Waldo's")),
    ("Labs4rescue", lambda: fetch_petfinder_org("CT178", "Labs4rescue")),
    ("ACC Manhattan", lambda: fetch_petfinder_org("NY12", "ACC Manhattan")),
    # Any Petfinder org works — the code is in its member URL:
    #   ("Animal Haven", lambda: fetch_petfinder_org("NY17", "Animal Haven")),
    #   ("NYC Second Chance", lambda: fetch_petfinder_org("NY949", "Second Chance")),
]
