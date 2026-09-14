"""Phase 1 tests: Indian plants catalogue + enriched species API."""

from data.indian_plants import (
    display_name_for,
    find_by_scientific,
    list_categories,
    load_catalogue,
    search_catalogue,
)


def test_catalogue_loads_and_validates():
    entries = load_catalogue()
    assert len(entries) >= 50
    ids = [e["id"] for e in entries]
    assert len(set(ids)) == len(ids)


def test_tulsi_search_all_three_scripts():
    for q in ("tulsi", "तुलसी", "તુલસી"):
        hits = search_catalogue(q)
        assert hits, f"no hits for {q!r}"
        assert hits[0]["scientific_name"] == "Ocimum tenuiflorum"
        assert hits[0]["indian_names"]["hi"] == "तुलसी"
        assert hits[0]["indian_names"]["gu"] == "તુલસી"


def test_display_name_per_lang():
    entry = find_by_scientific("Ocimum tenuiflorum")
    assert display_name_for(entry, "hi") == "तुलसी"
    assert display_name_for(entry, "gu") == "તુલસી"
    assert display_name_for(entry, "en") == "Tulsi"


def test_category_kind_filters():
    seeds = search_catalogue("", kind="seed", limit=100)
    assert seeds
    assert all(h["kind"] == "seed" for h in seeds)
    veg = search_catalogue("", category="vegetable", limit=100)
    assert veg
    assert all(h["category"] == "vegetable" for h in veg)


def test_categories_endpoint(client, auth_headers):
    resp = client.get("/plants/categories", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = {c["name"] for c in data}
    assert {"vegetable", "spice", "fruit"} <= names
    assert all(c["count"] >= 1 for c in data)


def test_indian_catalogue_no_key_needed(client, auth_headers):
    resp = client.get("/plants/indian-catalogue", params={"q": "methi"}, headers=auth_headers)
    assert resp.status_code == 200
    hits = resp.json()
    assert hits
    assert any(h["scientific_name"] == "Trigonella foenum-graecum" for h in hits)
    first = hits[0]
    assert first["source"] == "indian_catalogue"
    assert first["display_name"]
    assert first["indian_names"]["hi"]


def test_search_species_includes_catalogue_without_external_keys(client, auth_headers):
    # No Perenual/FloraCodex keys in test env — catalogue must still answer.
    resp = client.get(
        "/plants/species/search", params={"q": "haldi"}, headers=auth_headers
    )
    assert resp.status_code == 200
    hits = resp.json()
    assert any(h["scientific_name"] == "Curcuma longa" for h in hits)
    haldi = next(h for h in hits if h["scientific_name"] == "Curcuma longa")
    assert haldi["display_name"]
    assert haldi["indian_names"]["hi"] == "हल्दी"


def test_search_species_lang_display_name(client, auth_headers):
    resp = client.get(
        "/plants/species/search",
        params={"q": "tulsi", "lang": "hi"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    tulsi = next(h for h in resp.json() if h["scientific_name"] == "Ocimum tenuiflorum")
    assert tulsi["display_name"] == "तुलसी"


def test_search_species_filters_and_validation(client, auth_headers):
    resp = client.get(
        "/plants/species/search",
        params={"q": "", "kind": "seed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert all(h["kind"] == "seed" for h in resp.json())

    bad = client.get(
        "/plants/species/search", params={"q": "tulsi", "lang": "fr"}, headers=auth_headers
    )
    assert bad.status_code == 422
    bad_cat = client.get(
        "/plants/species/search",
        params={"q": "tulsi", "category": "nope"},
        headers=auth_headers,
    )
    assert bad_cat.status_code == 422


def test_backward_compat_fields_present(client, auth_headers):
    resp = client.get(
        "/plants/species/search", params={"q": "tulsi"}, headers=auth_headers
    )
    assert resp.status_code == 200
    hit = resp.json()[0]
    for field in ("id", "common_name", "scientific_name", "source"):
        assert field in hit
