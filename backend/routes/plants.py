import asyncio
import os
import uuid
from datetime import datetime

import aiofiles
import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai import (
    CareAdvisor,
    CareProviderError,
    CareRecommendation,
    PlantIdentity,
    ProviderNotConfigured,
)
from core.database import get_db
from core.security import get_current_user
from data.indian_plants import (
    VALID_CATEGORIES,
    VALID_KINDS,
    VALID_LANGS,
    catalogue_to_species,
    enrich_species,
    find_by_id,
    find_by_scientific,
    list_categories,
    search_catalogue,
)
from models.plant import Plant
from models.user import User

router = APIRouter(prefix="/plants", tags=["plants"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

WATERING_TO_DAYS = {"Frequent": 2, "Average": 7, "Minimum": 14, "None": 30}


def _clean(value):
    """Return None if Perenual returned a paywall/upgrade message, otherwise the value."""
    if isinstance(value, str) and value.startswith("Upgrade Plans"):
        return None
    return value


def _clean_list(value) -> list[str] | None:
    """Normalise sunlight/etc which may be a list or a paywall string."""
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [
            v
            for v in value
            if not (isinstance(v, str) and v.startswith("Upgrade Plans"))
        ]
        return cleaned or None
    return None  # was a paywall string


class IndianNames(BaseModel):
    hi: str | None = None
    gu: str | None = None
    hi_translit: str | None = None
    gu_translit: str | None = None


class SpeciesResult(BaseModel):
    id: str
    common_name: str
    scientific_name: str
    thumbnail: str | None
    watering: str | None
    watering_days: int | None
    sunlight: list[str] | None
    cycle: str | None
    description: str | None
    source: str = "perenual"  # perenual | inaturalist | floracodex | indian_catalogue
    # Phase 1 — Indian catalogue enrichment (optional, backward compatible).
    indian_names: IndianNames | None = None
    display_name: str | None = None
    category: str | None = None
    kind: str | None = None  # plant | seed


def _check_lang(lang: str) -> str:
    lang = (lang or "en").lower()
    if lang not in VALID_LANGS:
        raise HTTPException(status_code=422, detail="lang must be one of: en, hi, gu")
    return lang


def _check_category(category: str | None) -> str | None:
    if category is None:
        return None
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown category: {category}. Valid: {sorted(VALID_CATEGORIES)}",
        )
    return category


def _check_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail="kind must be one of: plant, seed")
    return kind


def _enrich(result: SpeciesResult, lang: str) -> SpeciesResult:
    data = enrich_species(result.model_dump(), lang=lang)
    return SpeciesResult(**data)


def _passes_filters(
    result: SpeciesResult, category: str | None, kind: str | None
) -> bool:
    if category and result.category != category:
        return False
    if kind and result.kind != kind:
        return False
    return True


def _resolve_api_key(
    key_name: str, user_id: int, db: Session, *, allow_env_fallback: bool = True
) -> str | None:
    """Read API key from user settings first, fall back to environment variable.

    Pass allow_env_fallback=False for demo users to prevent them from using
    server-level API keys at the operator's expense.
    """
    from core.crypto import decrypt_value
    from models.setting import Setting

    row = (
        db.query(Setting)
        .filter(Setting.user_id == user_id, Setting.key == key_name)
        .first()
    )
    if row and row.value:
        return decrypt_value(row.value)
    if allow_env_fallback:
        return os.getenv(key_name.upper())
    return None


async def _search_perenual(q: str, api_key: str) -> list[SpeciesResult]:
    """Search Perenual. Returns [] on any error so other sources can still contribute."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://perenual.com/api/species-list",
                params={"key": api_key, "q": q, "page": 1},
            )
            if not resp.is_success:
                return []
            data = resp.json().get("data", [])
        results = []
        for item in data[:10]:
            watering = _clean(item.get("watering"))
            sci = item.get("scientific_name", [])
            results.append(
                SpeciesResult(
                    id=str(item["id"]),
                    common_name=item.get("common_name", ""),
                    scientific_name=sci[0] if sci else "",
                    thumbnail=item.get("default_image", {}).get("thumbnail")
                    if item.get("default_image")
                    else None,
                    watering=watering,
                    watering_days=WATERING_TO_DAYS.get(watering),
                    sunlight=_clean_list(item.get("sunlight")),
                    cycle=_clean(item.get("cycle")),
                    description=None,
                    source="perenual",
                )
            )
        return results
    except Exception:
        return []


async def _search_inaturalist(q: str) -> list[SpeciesResult]:
    """Search iNaturalist taxa. No API key required."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.inaturalist.org/v1/taxa",
                params={"q": q, "rank": "species", "taxon_id": 47126, "per_page": 10},
                headers={"User-Agent": "SproutApp/1.0"},
            )
            if not resp.is_success:
                return []
        results = []
        for item in resp.json().get("results", []):
            photo = item.get("default_photo") or {}
            results.append(
                SpeciesResult(
                    id=str(item["id"]),
                    common_name=item.get("preferred_common_name") or "",
                    scientific_name=item.get("name", ""),
                    thumbnail=photo.get("square_url"),
                    watering=None,
                    watering_days=None,
                    sunlight=None,
                    cycle=None,
                    description=None,
                    source="inaturalist",
                )
            )
        return results
    except Exception:
        return []


async def _search_floracodex(q: str, api_key: str) -> list[SpeciesResult]:
    """Search FloraCodex. Returns [] on any error."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.floracodex.com/v1/species/search",
                params={"q": q, "limit": 10, "page": 0, "key": api_key},
                headers={"User-Agent": "SproutApp/1.0"},
            )
            if not resp.is_success:
                return []
        results = []
        for item in resp.json().get("data", []):
            results.append(
                SpeciesResult(
                    id=str(item["id"]),
                    common_name=item.get("common_name") or "",
                    scientific_name=item.get("scientific_name", ""),
                    thumbnail=item.get("image_url"),
                    watering=None,
                    watering_days=None,
                    sunlight=None,
                    cycle=None,
                    description=None,
                    source="floracodex",
                )
            )
        return results
    except Exception:
        return []


@router.get("/species/search", response_model=list[SpeciesResult])
async def search_species(
    q: str,
    lang: str = "en",
    category: str | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = _check_lang(lang)
    category = _check_category(category)
    kind = _check_kind(kind)
    env_ok = not current_user.is_demo
    perenual_key = _resolve_api_key(
        "perenual_api_key", current_user.id, db, allow_env_fallback=env_ok
    )
    floracodex_key = _resolve_api_key(
        "floracodex_api_key", current_user.id, db, allow_env_fallback=env_ok
    )

    tasks = [_search_inaturalist(q)]
    if perenual_key:
        tasks.append(_search_perenual(q, perenual_key))
    if floracodex_key:
        tasks.append(_search_floracodex(q, floracodex_key))

    all_results = await asyncio.gather(*tasks)

    # Merge: Perenual first (has care data), then iNaturalist, then FloraCodex.
    # Deduplicate by lowercase scientific name — keep first occurrence.
    perenual = all_results[1] if perenual_key else []
    inat = all_results[0]
    floracodex = (
        all_results[-1]
        if floracodex_key and len(all_results) > (2 if perenual_key else 1)
        else []
    )

    seen: set[str] = set()
    merged: list[SpeciesResult] = []
    for result in [*perenual, *inat, *floracodex]:
        key = result.scientific_name.lower().strip()
        if key and key not in seen:
            seen.add(key)
            enriched = _enrich(result, lang)
            if _passes_filters(enriched, category, kind):
                merged.append(enriched)

    # Catalogue-first: local Indian names need no API key, so a Tulsi search
    # works even when Perenual/FloraCodex keys are missing (demo/offline).
    try:
        catalogue_hits = search_catalogue(
            q, category=category, kind=kind, lang=lang, limit=20
        )
    except Exception:
        catalogue_hits = []
    for hit in catalogue_hits:
        key = (hit.get("scientific_name") or "").lower().strip()
        hit_result = SpeciesResult(**hit)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(hit_result)

    return merged[:20]


class CategoryOut(BaseModel):
    name: str
    count: int


@router.get("/categories", response_model=list[CategoryOut])
def get_categories(current_user: User = Depends(get_current_user)):
    """List Indian catalogue categories with entry counts. No API key needed."""
    return list_categories()


@router.get("/indian-catalogue", response_model=list[SpeciesResult])
def get_indian_catalogue(
    q: str = "",
    category: str | None = None,
    kind: str | None = None,
    lang: str = "en",
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Paged Indian plants/seeds catalogue. Works without any external API key."""
    lang = _check_lang(lang)
    category = _check_category(category)
    kind = _check_kind(kind)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    hits = search_catalogue(
        q, category=category, kind=kind, lang=lang, limit=limit, offset=offset
    )
    return [SpeciesResult(**h) for h in hits]


class WikiDescription(BaseModel):
    description: str | None
    thumbnail: str | None


@router.get("/species/wiki-description", response_model=WikiDescription)
async def wiki_description(
    scientific_name: str,
    lang: str = "en",
    current_user: User = Depends(get_current_user),
):
    """Fetch description and thumbnail from Wikipedia — free, no API key required.

    Tries the requested language subdomain first (hi/gu), falls back to English.
    """
    lang = _check_lang(lang)
    wiki_name = scientific_name.replace(" ", "_")
    subdomains = [lang] if lang != "en" else []
    subdomains.append("en")
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            for sub in subdomains:
                resp = await client.get(
                    f"https://{sub}.wikipedia.org/api/rest_v1/page/summary/{wiki_name}",
                    headers={"User-Agent": "PlantaApp/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    sentences = extract.split(". ")
                    description = ". ".join(sentences[:3]).strip()
                    if description and len(sentences) > 3:
                        description += "."
                    thumbnail = (
                        data.get("thumbnail", {}).get("source")
                        if data.get("thumbnail")
                        else None
                    )
                    return {"description": description or None, "thumbnail": thumbnail}
    except Exception:
        pass
    return {"description": None, "thumbnail": None}


@router.post("/species/ai-care", response_model=CareRecommendation)
async def ai_care(
    body: PlantIdentity,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await CareAdvisor(db).recommend(
            body,
            user_id=current_user.id,
            allow_env_fallback=not current_user.is_demo,
        )
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CareProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _wikipedia_description(scientific_name: str, lang: str = "en") -> str | None:
    """Fetch a concise description from Wikipedia, trying `lang` first then English."""
    if lang not in VALID_LANGS:
        lang = "en"
    subdomains = [lang] if lang != "en" else []
    subdomains.append("en")
    try:
        wiki_name = scientific_name.replace(" ", "_")
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            for sub in subdomains:
                resp = await client.get(
                    f"https://{sub}.wikipedia.org/api/rest_v1/page/summary/{wiki_name}",
                    headers={"User-Agent": "PlantaApp/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    extract = data.get("extract", "")
                    # Return first two sentences to keep it concise
                    sentences = extract.split(". ")
                    return ". ".join(sentences[:3]).strip() + (
                        "." if len(sentences) > 3 else ""
                    )
    except Exception:
        pass
    return None


@router.get("/species/{species_id}", response_model=SpeciesResult)
async def get_species(
    species_id: str,
    source: str = "perenual",
    lang: str = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lang = _check_lang(lang)
    if source == "indian_catalogue":
        # Catalogue detail by id (e.g. id=indian-tulsi-plant) or scientific name.
        entry = find_by_id(species_id)
        if entry is None:
            entry = find_by_scientific(species_id.replace("_", " "))
        if entry is None:
            raise HTTPException(status_code=404, detail="Species not found")
        return SpeciesResult(**catalogue_to_species(entry, lang=lang))
    if source == "inaturalist":
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"https://api.inaturalist.org/v1/taxa/{species_id}",
                headers={"User-Agent": "SproutApp/1.0"},
            )
            resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            raise HTTPException(status_code=404, detail="Species not found")
        item = results[0]
        photo = item.get("default_photo") or {}
        scientific_name = item.get("name", "")
        description = await _wikipedia_description(scientific_name, lang)
        return _enrich(
            SpeciesResult(
                id=str(item["id"]),
                common_name=item.get("preferred_common_name") or "",
                scientific_name=scientific_name,
                thumbnail=photo.get("medium_url") or photo.get("square_url"),
                watering=None,
                watering_days=None,
                sunlight=None,
                cycle=None,
                description=description,
                source="inaturalist",
            ),
            lang,
        )

    if source == "floracodex":
        api_key = _resolve_api_key(
            "floracodex_api_key",
            current_user.id,
            db,
            allow_env_fallback=not current_user.is_demo,
        )
        if not api_key:
            raise HTTPException(
                status_code=503, detail="FloraCodex API key not configured."
            )
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"https://api.floracodex.com/v1/species/{species_id}",
                params={"key": api_key},
                headers={"User-Agent": "SproutApp/1.0"},
            )
            resp.raise_for_status()
        item = resp.json()
        scientific_name = item.get("scientific_name", "")
        common_name = item.get("common_name") or ""
        if not common_name:
            for cn in item.get("common_names", []):
                english = cn.get("ENGLISH") or cn.get("english") or []
                if english:
                    common_name = english[0]
                    break
        description = await _wikipedia_description(scientific_name, lang)
        return _enrich(
            SpeciesResult(
                id=str(item["id"]),
                common_name=common_name,
                scientific_name=scientific_name,
                thumbnail=item.get("image_url"),
                watering=None,
                watering_days=None,
                sunlight=None,
                cycle=None,
                description=description,
                source="floracodex",
            ),
            lang,
        )

    # Default: Perenual
    api_key = _resolve_api_key(
        "perenual_api_key",
        current_user.id,
        db,
        allow_env_fallback=not current_user.is_demo,
    )
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Perenual API key not configured.",
        )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://perenual.com/api/species/details/{species_id}",
            params={"key": api_key},
        )
        if resp.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Perenual daily request limit reached (100/day on free plan). Try again tomorrow.",
            )
        resp.raise_for_status()
        item = resp.json()
    watering = _clean(item.get("watering"))
    sci = item.get("scientific_name", [])
    scientific_name = sci[0] if sci else ""
    desc_sections = item.get("description", [])
    description = _clean(desc_sections[0].get("description") if desc_sections else None)
    if not description and scientific_name:
        description = await _wikipedia_description(scientific_name, lang)
    return _enrich(
        SpeciesResult(
            id=str(item["id"]),
            common_name=item.get("common_name", ""),
            scientific_name=scientific_name,
            thumbnail=item.get("default_image", {}).get("thumbnail")
            if item.get("default_image")
            else None,
            watering=watering,
            watering_days=WATERING_TO_DAYS.get(watering),
            sunlight=_clean_list(item.get("sunlight")),
            cycle=_clean(item.get("cycle")),
            description=description,
            source="perenual",
        ),
        lang,
    )


class PlantOut(BaseModel):
    id: int
    name: str
    species: str | None
    photo_url: str | None
    location: str | None
    notes: str | None
    acquired_on: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class PlantCreate(BaseModel):
    name: str
    species: str | None = None
    photo_url: str | None = None
    location: str | None = None
    notes: str | None = None
    acquired_on: datetime | None = None


class PlantUpdate(BaseModel):
    name: str | None = None
    species: str | None = None
    location: str | None = None
    notes: str | None = None
    acquired_on: datetime | None = None


class PlantHealthSummary(BaseModel):
    plant_id: int
    health: str


@router.get("/health-summary", response_model=list[PlantHealthSummary])
def health_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent journal-entry health value for each of the user's plants."""
    from sqlalchemy import func

    from models.journal import JournalEntry

    subq = (
        db.query(
            JournalEntry.plant_id,
            func.max(JournalEntry.entry_date).label("max_date"),
        )
        .join(Plant, Plant.id == JournalEntry.plant_id)
        .filter(Plant.owner_id == current_user.id, JournalEntry.health.isnot(None))
        .group_by(JournalEntry.plant_id)
        .subquery()
    )
    rows = (
        db.query(JournalEntry.plant_id, JournalEntry.health)
        .join(
            subq,
            (JournalEntry.plant_id == subq.c.plant_id)
            & (JournalEntry.entry_date == subq.c.max_date),
        )
        .all()
    )
    return [{"plant_id": r.plant_id, "health": r.health} for r in rows]


@router.get("/", response_model=list[PlantOut])
def list_plants(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return db.query(Plant).filter(Plant.owner_id == current_user.id).all()


async def _mirror_photo(url: str) -> str | None:
    """Download an external photo URL and save it locally; return the local path."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "PlantaApp/1.0"})
            resp.raise_for_status()
        ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        filename = f"{uuid.uuid4()}{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        async with aiofiles.open(path, "wb") as f:
            await f.write(resp.content)
        return f"/uploads/{filename}"
    except Exception:
        return url  # fall back to original URL rather than losing the photo


@router.post("/", response_model=PlantOut, status_code=201)
async def create_plant(
    data: PlantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.photo_url and data.photo_url.startswith("http"):
        data = data.model_copy(
            update={"photo_url": await _mirror_photo(data.photo_url)}
        )
    plant = Plant(**data.model_dump(), owner_id=current_user.id)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.get("/{plant_id}", response_model=PlantOut)
def get_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = (
        db.query(Plant)
        .filter(Plant.id == plant_id, Plant.owner_id == current_user.id)
        .first()
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    return plant


@router.patch("/{plant_id}", response_model=PlantOut)
def update_plant(
    plant_id: int,
    data: PlantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = (
        db.query(Plant)
        .filter(Plant.id == plant_id, Plant.owner_id == current_user.id)
        .first()
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(plant, field, value)
    db.commit()
    db.refresh(plant)
    return plant


@router.delete("/{plant_id}", status_code=204)
def delete_plant(
    plant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = (
        db.query(Plant)
        .filter(Plant.id == plant_id, Plant.owner_id == current_user.id)
        .first()
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    db.delete(plant)
    db.commit()


@router.post("/{plant_id}/photo", response_model=PlantOut)
async def upload_photo(
    plant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plant = (
        db.query(Plant)
        .filter(Plant.id == plant_id, Plant.owner_id == current_user.id)
        .first()
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Plant not found")
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    async with aiofiles.open(path, "wb") as f:
        await f.write(await file.read())
    plant.photo_url = f"/uploads/{filename}"
    db.commit()
    db.refresh(plant)
    return plant
