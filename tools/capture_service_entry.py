"""Role-specific service entry: one protected secret file, one fixed worker.

No secret is placed in a plist or command line. Provision separate OS identities
and protected ancestor paths before activation. This command performs real work.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import stat
import sys

from tools.capture_private_service import PRIVATE_ENV
from tools.model_worker import MODEL_ENV
from tools.reference_worker import REFERENCE_ENV

ENVIRONMENTS={'private':PRIVATE_ENV,'nightly':PRIVATE_ENV,'model':MODEL_ENV,'reference':REFERENCE_ENV}
ALL_CREDENTIALS=set(PRIVATE_ENV+MODEL_ENV+REFERENCE_ENV+('SUPABASE_SERVICE_ROLE_KEY',))
ROOT=Path(__file__).resolve().parents[1]


def credentials(path,role):
    allowed=ENVIRONMENTS[role]
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
            or info.st_mode & 0o077 or info.st_size>16384):
            raise ValueError('private owner-only secret file required')
        with os.fdopen(fd,'rb',closefd=False) as stream:body=stream.read(16385)
        if len(body)>16384:raise ValueError('secret configuration too large')
        value=json.loads(body)
        if (not isinstance(value,dict) or not value or set(value)-set(allowed)
            or any(not isinstance(v,str) or not v or '\x00' in v for v in value.values())):
            raise ValueError('invalid role configuration')
        required=({'SUPABASE_DB_URL'} if role in ('private','nightly') else
                  {'MODEL_EGRESS_DB_URL','CF_API_TOKEN','CF_ACCOUNT_ID'} if role=='model' else
                  {'REFERENCE_EGRESS_DB_URL'})
        if not required<=value.keys():raise ValueError('missing role credentials')
        return value
    finally:os.close(fd)


def command(role,root):
    root=Path(root)
    if not root.is_absolute():raise ValueError('absolute runtime root required')
    if role in ('private','nightly'):
        args=[sys.executable,'-m','tools.capture_private_service']
        for flag,path in [('state-directory','private-state'),('model-outbox','model-outbox'),
                          ('model-results','model-results'),('reference-outbox','reference-outbox')]:
            args.extend(['--'+flag,str(root/path)])
        if role=='nightly':args.append('--retry')
        return args
    if role not in ('model','reference'):raise ValueError('invalid role')
    return [sys.executable,'-m','tools.capture_dispatch_mailbox',role,
            str(root/(role+'-outbox')),str(root/(role+'-results')),
            '--state-directory',str(root/(role+'-state')),'--limit','1']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=tuple(ENVIRONMENTS))
    parser.add_argument('--secrets',required=True)
    parser.add_argument('--runtime-root',required=True)
    args=parser.parse_args()
    try:
        if os.environ.get('PERSONAL_OS_TEST_SOCKET') or any(os.environ.get(k) for k in ALL_CREDENTIALS):
            raise ValueError('service manager must not preload credentials')
        # UTC06:00 is01:00/02:00 in New York. The database daily gate holds after
        # the sweep finishes; later ticks complete long/interrupted sweeps.
        if args.role=='nightly' and dt.datetime.now(dt.timezone.utc).hour<6:
            print(json.dumps({'status':'not_due'}));return 0
        env=credentials(args.secrets,args.role)
        env['PYTHONPATH']=str(ROOT)
        argv=command(args.role,args.runtime_root)
        os.chdir(ROOT)
        os.execve(sys.executable,argv,env)
    except Exception:
        print(json.dumps({'status':'error','error_type':'CaptureServiceConfigurationUnavailable'}),file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
