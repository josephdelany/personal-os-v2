"""Gate scope: private reference archives cannot hide active or tracked code."""
from pathlib import Path
import subprocess

import pytest
from tools.layout_sources import active_code_paths


@pytest.fixture
def repo(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    return tmp_path


def put(root,name):
    p=root/name
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('active fixture code')
    return p


def paths(root):
    return {rel for rel,_ in active_code_paths(root,suffixes=('.py','.sql'),skip_dirs=('.git',))}


def test_RULE_00_REQ_LOC_005_exact_reference_archive_boundary(repo):
    put(repo,'.local/project-library/worktrees/old.py')
    for name in ('.local/active.py','.local/project-library-copy/code.py','active.py',
                 'nested/.local/project-library/code.py'):
        put(repo,name)
    put(repo,'.gitignore').write_text('.local/\n')
    assert paths(repo)=={'.local/active.py','.local/project-library-copy/code.py',
                         'active.py','nested/.local/project-library/code.py'}


def test_RULE_00_RULE_29_tracked_archive_refused(repo):
    put(repo,'.local/project-library/code.py')
    subprocess.run(['git','add','.local/project-library/code.py'],cwd=repo,check=True)
    with pytest.raises(ValueError,match='tracked'):
        paths(repo)


@pytest.mark.parametrize('directory',[False,True])
def test_RULE_00_REQ_LOC_005_active_archive_symlink_refused(repo,directory):
    target=put(repo,'.local/project-library/code.py')
    (repo/('alias' if directory else 'alias.py')).symlink_to(target.parent if directory else target)
    with pytest.raises(ValueError,match='active symlink'):
        paths(repo)


def test_RULE_00_RULE_29_archive_boundary_symlink_refused(repo):
    target=repo/'reference'
    target.mkdir()
    (repo/'.local').mkdir()
    (repo/'.local/project-library').symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='boundary'):
        paths(repo)


def test_RULE_00_RULE_29_reference_portal_is_exact_and_untracked(repo):
    target=put(repo,'.local/project-library/code.py').parent
    (repo/'Collected Files').symlink_to(target,target_is_directory=True)
    assert paths(repo)==set()
    subprocess.run(['git','add','Collected Files'],cwd=repo,check=True)
    with pytest.raises(ValueError,match='tracked'):
        paths(repo)


def test_RULE_00_REQ_LOC_005_reference_portal_cannot_target_archive_subdirectory(repo):
    target=put(repo,'.local/project-library/worktree/code.py').parent
    (repo/'Collected Files').symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='active symlink'):
        paths(repo)


def test_RULE_00_active_directory_error_fails_closed(repo,monkeypatch):
    import tools.layout_sources as scan
    def denied_walk(*args,**kwargs):
        kwargs['onerror'](PermissionError('fixture traversal denied'))
    monkeypatch.setattr(scan.os,'walk',denied_walk)
    with pytest.raises(PermissionError,match='traversal denied'):
        paths(repo)


def test_RULE_00_active_file_read_error_fails_closed(repo,monkeypatch):
    from tools.layout_sources import active_code_text
    put(repo,'active.py')
    def denied_read(*args,**kwargs):
        raise PermissionError('fixture read denied')
    monkeypatch.setattr(Path,'read_text',denied_read)
    with pytest.raises(PermissionError,match='read denied'):
        list(active_code_text(repo,suffixes=('.py',),skip_dirs=('.git',)))


def test_RULE_00_REQ_FIN_255_archive_scope_preserves_active_finance_guard(repo):
    from tools.engines.finance_never import scan_repository
    code='import '+'selen'+'ium\n'
    put(repo,'.local/project-library/old.py').write_text(code)
    active=put(repo,'.local/live.py')
    active.write_text(code)
    findings=scan_repository(repo)
    assert len(findings)==1 and findings[0].requirement=='REQ-FIN-255'
    assert findings[0].where==str(active)
