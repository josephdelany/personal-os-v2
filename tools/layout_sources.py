"""Active code boundary for layout checks (ADR0168)."""
import os
from pathlib import Path
import subprocess

ARCHIVE = Path('.local/project-library')
PORTAL = Path('Collected Files')


def _walk_error(error):
    raise error


def active_code_paths(root, *, suffixes, skip_dirs, exclude=()):
    root = Path(root).resolve()
    archive = root / ARCHIVE
    if (root / '.local').is_symlink() or archive.is_symlink():
        raise ValueError('project-library archive boundary must not be a symlink')
    # A standalone scanner fixture with no archive needs no Git repository.
    # Any repository or proposed archive boundary must establish tracking state.
    tracked = b''
    if (root / '.git').exists() or archive.exists() or (root / PORTAL).exists():
        tracked = subprocess.run(['git', 'ls-files', '-z', '--', ARCHIVE.as_posix(), PORTAL.as_posix()],
                                 cwd=root, check=True, capture_output=True).stdout
    if tracked:
        raise ValueError('project-library archive or reference portal contains root-tracked files')
    for base, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=_walk_error):
        base = Path(base)
        for name in dirs + files:
            path = base / name
            if path.is_symlink() and path.resolve().is_relative_to(archive):
                if path == root / PORTAL and path.resolve() == archive:
                    continue  # Exact user-created reference navigation portal.
                raise ValueError('active symlink points into project-library archive')
        dirs[:] = [name for name in dirs
                   if name not in skip_dirs and base / name != archive]
        for name in files:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if rel in exclude or not rel.lower().endswith(suffixes):
                continue
            if path.is_file():
                yield rel, path


def active_code_text(root, **kwargs):
    for rel, path in active_code_paths(root, **kwargs):
        yield rel, path.read_text(errors='ignore')
