import time
from pathlib import Path


def purge_old_files(directory: Path, max_age_days: int = 7) -> list[Path]:
    """Delete files in `directory` whose mtime is older than `max_age_days`.

    Returns the list of deleted paths. Non-recursive; ignores subdirectories.
    """
    cutoff = time.time() - max_age_days * 86400
    deleted = []
    if not directory.exists():
        return deleted
    for path in directory.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            deleted.append(path)
    return deleted
