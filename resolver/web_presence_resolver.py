"""
Web presence resolver -- checks OSM/Geoapify raw tags for social media links
and sets the contactable flag.

Works identically regardless of which provider found the lead, because both
providers standardize _raw_tags to use the same normalized keys (Fix #1).
"""

import logging

logger = logging.getLogger(__name__)


def resolve_web_presence(leads: list[dict]) -> list[dict]:
    """
    For each lead, resolve web presence from raw tags and set contactable flag.

    Steps for each lead:
    1. If website is missing, check _raw_tags for social media links
    2. Store found social URLs in the facebook/instagram/linkedin fields
    3. Set contactable = True if phone OR email is present
    4. Strip _raw_tags from the dict (internal-only, not stored in DB)

    Args:
        leads: List of lead dicts with _raw_tags from discovery providers.

    Returns:
        List of lead dicts with social fields populated and contactable set.
    """
    resolved = []

    for lead in leads:
        lead = dict(lead)  # Don't mutate the original
        raw_tags = lead.pop("_raw_tags", {})

        # Resolve social links from raw tags (Fix #1: normalized keys)
        if raw_tags.get("contact:facebook") and not lead.get("facebook"):
            lead["facebook"] = raw_tags["contact:facebook"]
            logger.debug("Resolved Facebook for %r: %s", lead.get("business_name"), lead["facebook"])

        if raw_tags.get("contact:instagram") and not lead.get("instagram"):
            lead["instagram"] = raw_tags["contact:instagram"]
            logger.debug("Resolved Instagram for %r: %s", lead.get("business_name"), lead["instagram"])

        if raw_tags.get("contact:linkedin") and not lead.get("linkedin"):
            lead["linkedin"] = raw_tags["contact:linkedin"]
            logger.debug("Resolved LinkedIn for %r: %s", lead.get("business_name"), lead["linkedin"])

        # Set contactable flag (Fix #5: only ever set to True, never back to False)
        # Phase 2 crawler must also respect this monotonicity.
        has_phone = bool(lead.get("phone"))
        has_email = bool(lead.get("email"))
        lead["contactable"] = has_phone or has_email

        # Strip internal fields
        lead.pop("_source", None)

        resolved.append(lead)

    # Stats
    contactable_count = sum(1 for l in resolved if l.get("contactable"))
    social_count = sum(1 for l in resolved if any([l.get("facebook"), l.get("instagram"), l.get("linkedin")]))
    logger.info(
        "Web presence resolved: %d leads, %d contactable, %d with social links",
        len(resolved), contactable_count, social_count,
    )

    return resolved
