"""Local role-to-role handoff. Provision each directory for one writer/reader group.

Requests are immutable create-if-absent files; result files are replaceable control
projections. Neither is authoritative capture evidence: committed SQL owns that.
No directory is created or permission broadened by this module.
"""
import contextlib
import fcntl
import hashlib
import json
import os
import stat
import uuid
from lib.model_contract import request_bytes

MAX_BYTES=72*1024*1024


def _name(request_id):
    canonical=str(uuid.UUID(str(request_id)))
    if canonical!=request_id: raise ValueError('canonical request identity required')
    return canonical+'.json'


@contextlib.contextmanager
def _directory(path,*,write=False):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if info.st_mode & 0o027 or (write and info.st_uid!=os.geteuid()):
            raise ValueError('mailbox requires one owner writer and no public access')
        if write:fcntl.flock(fd,fcntl.LOCK_EX)
        yield fd
    finally:os.close(fd)


def _read(directory,name):
    # Inspect special files without blocking on a FIFO before fstat can reject it.
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    try:
        info=os.fstat(fd)
        parent=os.fstat(directory)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o027
            or info.st_uid!=parent.st_uid or info.st_gid!=parent.st_gid or info.st_size>MAX_BYTES):
            raise ValueError('invalid mailbox file')
        with os.fdopen(fd,'rb',closefd=False) as stream:body=stream.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:raise ValueError('mailbox file too large')
        value=json.loads(body)
        if request_bytes(value)!=body:raise ValueError('noncanonical mailbox file')
        return value,body
    finally:os.close(fd)


def _write(directory,name,value,*,replace=False):
    body=request_bytes(value)
    if len(body)>MAX_BYTES:raise ValueError('mailbox file too large')
    temp='.tmp-'+str(uuid.uuid4())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
    try:
        # Each channel has a different reader group. The writer's primary group
        # need not be that group (and Linux need not inherit a directory's gid).
        os.fchown(fd,-1,os.fstat(directory).st_gid)
        os.fchmod(fd,0o640)
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(body);stream.flush();os.fsync(fd)
        if replace:
            os.replace(temp,name,src_dir_fd=directory,dst_dir_fd=directory)
        else:
            try:os.link(temp,name,src_dir_fd=directory,dst_dir_fd=directory,follow_symlinks=False)
            except FileExistsError:
                if _read(directory,name)[1]!=body:raise ValueError('mailbox request identity reused')
        os.fsync(directory)
    finally:
        os.close(fd)
        try:os.unlink(temp,dir_fd=directory)
        except FileNotFoundError:pass


def publish(directory,request):
    name=_name(request['request_id'])
    with _directory(directory,write=True) as fd:_write(fd,name,request)


def read(directory,request_id):
    with _directory(directory) as fd:value,_=_read(fd,_name(request_id))
    if not isinstance(value,dict) or value.get('request_id')!=request_id:
        raise ValueError('mailbox identity mismatch')
    return value


def pending(directory):
    with _directory(directory) as fd:names=os.listdir(fd)
    result=[]
    for name in names:
        if not name.endswith('.json'):continue
        try:_name(name[:-5])
        except ValueError:raise ValueError('invalid mailbox entry') from None
        result.append(name[:-5])
    return sorted(result)


def store_result(directory,request,result):
    if not isinstance(result,dict) or result.get('request_id')!=request['request_id']:
        raise ValueError('unbound worker result')
    value={'version':1,'request_sha256':hashlib.sha256(request_bytes(request)).hexdigest(),'result':result}
    with _directory(directory,write=True) as fd:_write(fd,_name(request['request_id']),value,replace=True)


def result(directory,request):
    with _directory(directory) as fd:value,_=_read(fd,_name(request['request_id']))
    if (not isinstance(value,dict) or set(value)!={'version','request_sha256','result'} or value['version']!=1
        or value['request_sha256']!=hashlib.sha256(request_bytes(request)).hexdigest()
        or not isinstance(value['result'],dict) or value['result'].get('request_id')!=request['request_id']):
        raise ValueError('unbound mailbox result')
    return value['result']


def retire(directory,request):
    """Caller must first commit the corresponding private SQL outcome."""
    with _directory(directory,write=True) as fd:
        name=_name(request['request_id'])
        if _read(fd,name)[1]!=request_bytes(request):raise ValueError('retirement identity mismatch')
        os.unlink(name,dir_fd=fd);os.fsync(fd)
