"""REQ-CAP-026 / RULE-29: generated scheduling packet, not deployed evidence."""
import plistlib
import pytest
from ops.capture_services import packet


def config(**changes):
    args=dict(repo='/srv/personal-os',python='/srv/venv/bin/python',runtime_root='/var/lib/capture',
              private_user='capture_private',model_user='capture_model',reference_user='capture_reference')
    args.update(changes)
    return packet(**args)


def test_REQ_CAP_026_RULE_29_packet_separates_roles_without_inline_secrets():
    result=config()
    assert set(result)=={'private','nightly','model','reference'}
    for role,value in result.items():
        assert plistlib.loads(plistlib.dumps(value))==value
        owner='private' if role=='nightly' else role
        assert value['UserName']=='capture_'+owner
        assert value['StartInterval']==60 and value['RunAtLoad'] is False
        assert value['EnvironmentVariables']=={'PYTHONPATH':'/srv/personal-os'}
        args=value['ProgramArguments']
        assert args[2:4]==['tools.capture_service_entry',role]
        assert args[args.index('--secrets')+1]=='/var/lib/capture/secrets/'+owner+'.json'


@pytest.mark.parametrize('changes',[{'model_user':'root'},{'reference_user':'capture_model'},
                                  {'repo':'relative'},{'private_user':'user; command'}])
def test_RULE_29_invalid_service_identity_or_relative_path_refuses(changes):
    with pytest.raises(ValueError):config(**changes)
