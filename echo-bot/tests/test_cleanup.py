import os
import time

from utils.cleanup import purge_old_files


def test_purge_deletes_old_files(tmp_path):
    old_file = tmp_path / 'old.log'
    new_file = tmp_path / 'new.log'
    old_file.write_text('old')
    new_file.write_text('new')

    old_time = time.time() - 8 * 86400
    os.utime(old_file, (old_time, old_time))

    deleted = purge_old_files(tmp_path, max_age_days=7)

    assert old_file.name in [p.name for p in deleted]
    assert not old_file.exists()
    assert new_file.exists()


def test_purge_missing_directory_returns_empty(tmp_path):
    missing = tmp_path / 'does_not_exist'
    assert purge_old_files(missing, max_age_days=7) == []


def test_purge_ignores_subdirectories(tmp_path):
    sub = tmp_path / 'subdir'
    sub.mkdir()
    old_time = time.time() - 8 * 86400
    os.utime(sub, (old_time, old_time))

    deleted = purge_old_files(tmp_path, max_age_days=7)

    assert deleted == []
    assert sub.exists()
