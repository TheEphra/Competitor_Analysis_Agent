
"""Collect basic, public website signals for competitor comparison."""

from datetime import datetime, timezone
from urllib.parse import urlparse
import ipaddress
import socket

import requests
from bs4 import BeautifulSoup


USER_AGENT = (
    "CompetitorAnalysisAgent/1.0 "
    "(educational website analysis)"
)
TIMEOUT_SECONDS = 12
MAX_BYTES = 1_000_000


def validate_public_url(url: str) -> str:
    """Validate a public HTTP(S) URL before requesting it."""
    url = url.strip()
    parsed = urlparse(url if "://" in url else f"https://{url}")

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only HTTP and HTTPS websites are supported.")

    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a valid public website URL.")

    host = parsed.hostname.lower()

    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Local websites are not supported.")

    try:
        addresses = socket.getaddrinfo(
            host, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as exc:
        raise ValueError("The website hostname could not be resolved.") from exc

    if not addresses:
        raise ValueError("The website hostname could not be resolved.")

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private or non-public addresses are not supported.")

    return parsed.geturl()


def analyze_website(name: str, website: str) -> dict:
    """Analyze a small set of observable website signals."""
    result = {
        "Business": name,
        "Website": website,
        "Status": "Failed",
        "Title": "",
        "Meta Description": "",
        "H1 Count": None,
        "Heading Count": None,
        "Word Count": None,
        "HTTPS": None,
        "Contact Signal": None,
        "Website Score": None,
        "Coverage": "0/6 signals",
        "Evidence": "",
        "Analyzed At (UTC)": datetime.now(timezone.utc).isoformat(),
    }

    try:
        safe_url = validate_public_url(website)

        # Do not follow redirects automatically: each destination would
        # need to be validated separately to avoid unsafe redirects.
        with requests.get(
            safe_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=False,
        ) as response:
            result["HTTPS"] = safe_url.startswith("https://")

            if response.is_redirect:
                result["Status"] = "Redirect not followed"
                result["Evidence"] = (
                    "Website returned a redirect. Add and validate its "
                    "destination before analyzing it."
                )
                return result

            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type:
                result["Status"] = "Skipped non-HTML"
                result["Evidence"] = "The response is not an HTML page."
                return result

            content = bytearray()
            for chunk in response.iter_content(chunk_size=16384):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    content = content[:MAX_BYTES]
                    break

        soup = BeautifulSoup(
    bytes(content).decode("utf-8", errors="replace"),
    "html.parser",
)
        

        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description_tag = soup.find(
            "meta", attrs={"name": lambda value: value and value.lower() == "description"}
        )
        description = (
            description_tag.get("content", "").strip()
            if description_tag else ""
        )

        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        h1_count = len(soup.find_all("h1"))

        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()

        text = soup.get_text(" ", strip=True)
        words = text.split()
        contact_signal = any(
            marker in text.lower()
            for marker in ("contact us", "contact", "get in touch")
        )

        signals = {
            "Title present": bool(title),
            "Meta description present": bool(description),
            "H1 present": h1_count > 0,
            "Headings present": len(headings) > 0,
            "Text content present": len(words) >= 100,
            "Contact signal present": contact_signal,
        }

        score = round(100 * sum(signals.values()) / len(signals))

        result.update({
            "Status": "Analysed",
            "Title": title,
            "Meta Description": description,
            "H1 Count": h1_count,
            "Heading Count": len(headings),
            "Word Count": len(words),
            "Contact Signal": contact_signal,
            "Website Score": score,
            "Coverage": f"{len(signals)}/6 signals",
            "Evidence": "; ".join(
                f"{key}: {'yes' if value else 'no'}"
                for key, value in signals.items()
            ),
            "Analyzed At (UTC)": datetime.now(timezone.utc).isoformat(),
        })

    except (ValueError, requests.RequestException) as exc:
        result["Status"] = "Failed"
        result["Evidence"] = str(exc)

    return result
