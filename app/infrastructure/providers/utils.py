def dig(data, *path, default=None):
    """Safely walk a nested dict/list structure, returning `default` on any
    missing key/index/type mismatch.

    RapidAPI response shapes vary across plans/providers/versions, so detail
    extraction must degrade to None instead of crashing on a miss.
    """
    cur = data
    for key in path:
        try:
            cur = cur[key]
        except (KeyError, IndexError, TypeError):
            return default
    return cur if cur is not None else default
