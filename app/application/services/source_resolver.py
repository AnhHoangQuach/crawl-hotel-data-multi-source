from typing import List

from app.domain.exceptions import InvalidSourceError


def resolve_sources(raw: str, available_sources: List[str]) -> List[str]:
    """Turn a user-supplied source string ("all", or a comma-separated list)
    into a validated list of provider names.
    """
    if raw.strip().lower() == "all":
        return list(available_sources)

    requested = [s.strip().lower() for s in raw.split(",") if s.strip()]
    if not requested:
        raise InvalidSourceError("At least one source must be specified.")

    unknown = [s for s in requested if s not in available_sources]
    if unknown:
        raise InvalidSourceError(
            f"Unknown source(s): {unknown}. Available sources: {available_sources}"
        )
    return requested
