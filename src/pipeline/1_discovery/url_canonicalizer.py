"""URL Canonicalizer: Strips tracking parameters and generates deduplication fingerprints."""

import hashlib
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gh_jid",
    "gh_src",
    "ref",
    "lever-origin",
    "lever-source",
    "lever-source[]",
    "source",
    "mode",
    "iis",
    "iisn",
    "sessionId",
    "s",
    "trk",
    "trackingId",
}

COMPANY_SUFFIX_REGEX = re.compile(
    r"\b(inc\.?|llc\.?|corp\.?|corporation|ltd\.?|limited|co\.?|company)\b",
    re.IGNORECASE,
)

LOCATION_NOISE_REGEX = re.compile(
    r"[\(\[\{]\s*(?:remote|hybrid|onsite|on-site|flexible)\s*[\)\]\}]",
    re.IGNORECASE,
)


class URLCanonicalizer:
    """Canonicalizes job URLs and creates SHA-256 cross-channel deduplication fingerprints."""

    def canonicalize_url(self, raw_url: str) -> str:
        """Strip tracking parameters and normalize URL structure."""
        if not raw_url or not isinstance(raw_url, str):
            return ""

        url_str = raw_url.strip()
        parsed = urlparse(url_str)
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path

        # Case-insensitive path normalization for known ATS platforms
        if any(ats in netloc for ats in ("ashbyhq.com", "lever.co", "greenhouse.io")):
            path = path.lower()

        # Remove trailing slash for uniformity
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        # Filter out tracking query params
        query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
        clean_pairs = [
            (k, v) for k, v in query_pairs
            if k.lower() not in TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_") and not k.lower().startswith("lever-source")
        ]
        clean_query = urlencode(clean_pairs)

        return urlunparse((scheme, netloc, path, "", clean_query, ""))

    def generate_fingerprint(
        self,
        company: str,
        title: str,
        location: str = "",
    ) -> str:
        """Generate a canonical SHA-256 fingerprint for cross-channel job deduplication."""
        # Clean company name
        comp_clean = COMPANY_SUFFIX_REGEX.sub("", company or "").strip()
        comp_clean = re.sub(r"[^\w\s]", "", comp_clean).lower()
        comp_clean = re.sub(r"\s+", " ", comp_clean).strip()

        # Clean title
        title_clean = LOCATION_NOISE_REGEX.sub("", title or "").strip()
        title_clean = re.sub(r"[^\w\s]", "", title_clean).lower()
        title_clean = re.sub(r"\s+", " ", title_clean).strip()

        # Clean location (extract primary state/city token)
        loc_clean = LOCATION_NOISE_REGEX.sub("", location or "").strip()
        loc_clean = re.sub(r"[^\w\s]", "", loc_clean).lower()
        loc_clean = re.sub(r"\s+", " ", loc_clean).strip()

        raw_key = f"{comp_clean}::{title_clean}::{loc_clean}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
