"""Emit an uninstalled launchd daemon packet for independently credentialed roles."""
import argparse
from pathlib import Path
import plistlib
import re
import sys

ROLES=('private','nightly','model','reference')


def packet(*,repo,python,runtime_root,private_user,model_user,reference_user):
    paths=[Path(value) for value in (repo,python,runtime_root)]
    if not all(path.is_absolute() for path in paths):raise ValueError('absolute paths required')
    users={'private':private_user,'model':model_user,'reference':reference_user}
    if (len(set(users.values()))!=3 or any(user=='root' or not re.fullmatch('[a-z_][a-z0-9_-]*',user)
                                         for user in users.values())):
        raise ValueError('three distinct unprivileged service identities required')
    repo,python,runtime_root=paths
    result={}
    for role in ROLES:
        owner='private' if role=='nightly' else role
        result[role]={
            'Label':'com.personalos.capture-'+role,
            'UserName':users[owner],
            'ProgramArguments':[str(python),'-m','tools.capture_service_entry',role,
                '--secrets',str(runtime_root/'secrets'/(owner+'.json')),
                '--runtime-root',str(runtime_root)],
            'WorkingDirectory':str(repo),'EnvironmentVariables':{'PYTHONPATH':str(repo)},
            'StartInterval':60,'RunAtLoad':False,'ProcessType':'Background','LowPriorityIO':True,
            'StandardOutPath':str(runtime_root/(owner+'-logs')/(role+'.out')),
            'StandardErrorPath':str(runtime_root/(owner+'-logs')/(role+'.err'))}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=ROLES)
    for name in ('repo','python','runtime-root','private-user','model-user','reference-user'):
        parser.add_argument('--'+name,required=True)
    args=vars(parser.parse_args());role=args.pop('role')
    sys.stdout.buffer.write(plistlib.dumps(packet(**args)[role]))


if __name__=='__main__':main()
