"""Google Places (New) competitor discovery and CSV fallback."""

import csv
from difflib import get_close_matches
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.location"
USER_AGENT = "CompetitorAnalysisAgent/1.0 (educational competitor research project)"

INDUSTRY_QUERIES = {
    "salon": "hair salons and beauty salons", "hair salon": "hair salons",
    "beauty salon": "beauty salons", "barber": "barber shops", "barbershop": "barber shops",
    "spa": "spas and wellness centers", "restaurant": "restaurants", "cafe": "cafes",
    "bakery": "bakeries", "catering": "catering services", "hotel": "hotels",
    "guest house": "guest houses", "travel agency": "travel agencies",
    "digital marketing": "digital marketing agencies", "marketing": "marketing agencies",
    "advertising agency": "advertising agencies", "shop": "shops", "retail": "retail stores",
    "clothing store": "clothing stores", "jewelry store": "jewelry stores",
    "bookstore": "bookstores", "grocery store": "grocery stores", "electronics store": "electronics stores",
    "healthcare": "healthcare clinics", "clinic": "clinics", "hospital": "hospitals",
    "dentist": "dentists and dental clinics", "doctor": "doctors and medical practices",
    "pharmacy": "pharmacies", "gym": "gyms", "fitness": "fitness centers",
    "yoga studio": "yoga studios", "education": "schools and education centers",
    "school": "schools", "college": "colleges", "tutoring center": "tutoring centers",
    "real estate": "real estate agencies", "lawyer": "law firms and lawyers",
    "accountant": "accountants and accounting firms", "insurance agency": "insurance agencies",
    "auto repair": "auto repair shops", "car dealer": "car dealerships", "car wash": "car washes",
    "plumber": "plumbers", "electrician": "electricians", "contractor": "building contractors",
    "hardware store": "hardware stores", "moving company": "moving companies",
    "cleaning service": "cleaning services", "laundry": "laundromats and laundry services",
    "pet store": "pet stores", "veterinarian": "veterinary clinics", "pet groomer": "pet groomers",
    "photographer": "photographers and photography studios", "event venue": "event venues",
    "florist": "florists", "furniture store": "furniture stores", "mobile phone store": "mobile phone stores",
}


def discover_competitors(location: str, industry: str, limit: int = 15,
                         api_key: str | None = None) -> list[dict]:
    """Find businesses via Places Text Search (New); requires a configured key.

    No request is made when no key is available. A minimal field mask avoids
    requesting review, rating, phone, or other higher-tier data.
    """
    location, industry = (location or "").strip(), (industry or "").strip().casefold()
    if not location:
        raise ValueError("Enter a city or administrative area.")
    if not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20 (Google returns at most 20 per page).")
    # Correct near-miss spellings for known industries; for any other typed
    # industry, pass the user's phrase through to Google's text search.
    matched = get_close_matches(industry, INDUSTRY_QUERIES.keys(), n=1, cutoff=0.78)
    normalized_industry = matched[0] if matched else industry
    category = INDUSTRY_QUERIES.get(normalized_industry, industry)

    load_dotenv()
    key = (api_key or os.getenv("GOOGLE_PLACES_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("Google Places discovery needs GOOGLE_PLACES_API_KEY in your .env file. No live request was made.")

    try:
        response = requests.post(
            PLACES_SEARCH_URL,
            json={"textQuery": f"{category} in {location}", "pageSize": limit},
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": key,
                     "X-Goog-FieldMask": FIELD_MASK, "User-Agent": USER_AGENT},
            timeout=(8, 25),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Google Places could not be reached: {exc}") from exc
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(f"Google Places discovery failed (HTTP {response.status_code}). {detail}".strip())
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Google Places returned an invalid response.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("places", []), list):
        raise RuntimeError("Google Places returned an unexpected response format.")

    results, seen = [], set()
    for place in payload.get("places", [])[:limit]:
        name = str(place.get("displayName", {}).get("text", "")).strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        point = place.get("location") or {}
        results.append({
            "Business": name,
            "Website": str(place.get("websiteUri", "") or "").strip(),
            "Industry": normalized_industry.title(), "Location": location,
            "Address": str(place.get("formattedAddress", "") or ""),
            "Latitude": point.get("latitude"), "Longitude": point.get("longitude"),
            "Source": "Google Places API (New)",
        })
    return results


def load_competitors_from_csv(path: str = "data/sample_competitors.csv",
                              location: str | None = None,
                              industry: str | None = None) -> list[dict]:
    """Load CSV rows with Business, Website, Industry, Location columns."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("The CSV file is empty or has no header row.")
        columns = {c.strip().casefold(): c for c in reader.fieldnames if c}
        missing = [c for c in ("business", "website", "industry", "location") if c not in columns]
        if missing:
            raise ValueError("CSV is missing required columns: " + ", ".join(missing))
        results = []
        for row in reader:
            name = (row.get(columns["business"]) or "").strip()
            if not name:
                continue
            item = {"Business": name, "Website": (row.get(columns["website"]) or "").strip(),
                    "Industry": (row.get(columns["industry"]) or "").strip(),
                    "Location": (row.get(columns["location"]) or "").strip(),
                    "Latitude": (row.get(columns.get("latitude", ""), "") or ""),
                    "Longitude": (row.get(columns.get("longitude", ""), "") or ""),
                    "Source": (row.get(columns.get("source", ""), "") or "User-provided CSV").strip()}
            if location and item["Location"].casefold() != location.strip().casefold():
                continue
            if industry and item["Industry"].casefold() != industry.strip().casefold():
                continue
            results.append(item)
        return results
