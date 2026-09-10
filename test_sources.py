"""Regression tests. Run with: python test_sources.py"""
import types, sys
import sources as S, digest as D


class R:
    def __init__(self, d): self._d = d
    def json(self): return self._d


def test_petfinder_filters_to_adoptable():
    """Without adoption_status the search returns the org's entire history —
    600 dogs for Labs4rescue, all but 11 already adopted."""
    seen = {}
    calls = {"n": 0}

    def post(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return R({"data": {"organization": {"organizationId": "OID"}}})
        if calls["n"] == 2:
            seen.update(kw["json"]["variables"]["filters"])
            return R({"data": {"searchAnimal": {"animals": [{
                "animalId": "a1", "animalName": "Luca", "description": "Weight: 30lbs Age: 1yrs",
                "primaryPhotoId": "animal/a1/image/c.jpg", "_media": [{"mediaId": "c"}],
                "behavior": {"houseTrained": "Yes"},
                "physical": {"size": {"label": "Medium"}, "breed": {"primary": "Lab"},
                             "age": {"label": "Young"}},
                "publicUrl": {"url": "dog/luca-a1/ct/killingworth/labs-4-rescue-ct178"}}]}}})
        return R({"data": {"searchAnimal": {"animals": []}}})

    S.requests = types.SimpleNamespace(post=post, get=None)
    dogs = S.fetch_petfinder_org("CT178", "Labs4rescue")
    assert seen.get("adoption_status") == ["adoptable"], seen
    assert seen.get("organization_id") == ["OID"]
    assert dogs[0].url.startswith("https://www.petfinder.com/dog/")
    assert dogs[0].weight_lb == 30 and dogs[0].age_years == 1.0
    assert dogs[0].photos[0].endswith("c.jpg")
    print("  petfinder: adoptable-only filter, url, weight/age from prose  OK")


def test_small_puppy_stays_in_range():
    pup = S.Dog(source="x", uid="1", name="p", url="", age="6 months",
                age_years=0.5, size_bucket="Small", weight_note="Small (0-24)")
    grown = S.Dog(source="x", uid="2", name="g", url="", age="4 years",
                  age_years=4, size_bucket="Small", weight_note="Small (0-24)")
    assert D.in_size_range(pup) and not D.in_size_range(grown)
    print("  small dog under a year stays in range                        OK")


def test_negative_beats_positive():
    t = S.traits_from_text("I lived with children in my previous home. "
                           "I would do best in a home with only adult humans.")
    assert S.NO_KIDS in t and S.GOOD_KIDS not in t
    print("  a later negative overrides an earlier positive               OK")


def test_heic_dropped():
    payload = {"shelter_pets_total_page": 1, "shelter_pets": [{
        "pet_id": 1, "name": "x", "weight": "40lbs", "no_longer_available": False,
        "public_url": "/public/search/pet/1", "thumb_url": "https://s/a.jpg",
        "images": [{"thumb_url": "https://s/a.jpg"}, {"thumb_url": "https://s/b.HEIC"}],
        "description": ""}]}
    S.requests = types.SimpleNamespace(get=lambda *a, **k: R(payload), post=None)
    d = S.fetch_petstablished("1", "W")[0]
    assert not any("heic" in p.lower() for p in d.photos)
    assert d.url == "https://petstablished.com/public/search/pet/1"
    print("  petstablished: HEIC dropped, relative url absolutised        OK")


if __name__ == "__main__":
    print("running regression tests")
    for fn in [test_petfinder_filters_to_adoptable, test_small_puppy_stays_in_range,
               test_negative_beats_positive, test_heic_dropped]:
        fn()
    print("all passed")


def test_script_tag_cannot_escape_the_data_block():
    """A rescue write-up containing "</script>" must not close the tag.

    Everything on the page is built from text these five rescues type into
    their own admin panels. json.dumps alone does not escape "<", so a stray
    "</script>" in a description would end the script element and the rest of
    the payload would parse as HTML.
    """
    import digest
    from sources import Dog

    d = Dog(source="Test", uid="t1", name="</script><img src=x onerror=alert(1)>",
            url="https://example.com", photos=["https://example.com/a.jpg"],
            breed="Lab")
    page = digest.build_page([d], {})

    assert "</script><img" not in page
    assert "\\u003c/script>" in page
    # and the page still has exactly the one closing tag it shipped with
    assert page.count("</script>") == page.count("<script")
