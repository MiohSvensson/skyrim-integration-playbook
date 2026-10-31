"""Read-only positive/negative tests of the two exact source-format contracts."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from vfs_common import OWN, asset_key, digest, write_json
from legacy_nif_contracts import LegacyNifContracts, ASSETS, TEXTURES, CONTRACT_SHA
import nif_resource_inventory


def main():
    contract=LegacyNifContracts();checks=[]
    def check(name, function):
        function();checks.append({'case':name,'passed':True})
    def reject(function):
        try:function()
        except (ValueError,AssertionError,KeyError):return
        raise AssertionError('Expected exact contract rejection')
    for path,row in contract.entries.items():
        blob=Path(row['parsed_copy']).read_bytes()
        def positive():
            inv=contract.inventory(path,blob,row['provider'])
            assert inv['bs_version']==82 and len(inv['blocks'])==47
            assert inv['native_runtime_verified'] is False
            textures={asset_key(v,'texture',path) for b in inv['blocks'] for v in b.get('textures',[]) if v}
            assert textures==TEXTURES
        check(path+': exact source/block/texture proof',positive)
        check(path+': raw byte mutation rejected',lambda:reject(lambda:contract.inventory(path,blob[:-1]+bytes([blob[-1]^1]),row['provider'])))
        for name,value in [('kind','loose'),('archive_sha256','0'*64),('provider','Legacy of the Dragonborn'),
                           ('archive','DBM_Resources.bsa'),('entry','meshes/mwl/other.nif'),
                           ('sha256','0'*64),('archive_physical',str(OWN/'wrong.bsa'))]:
            location=dict(row['provider']);location[name]=value
            check(path+': changed winner '+name+' rejected',lambda location=location:reject(lambda:contract.inventory(path,blob,location)))
        check(path+': generic parser still rejects82',lambda:reject(lambda:nif_resource_inventory.inventory(row['parsed_copy'])))
    check('unknown path is never granted an inventory',lambda:assert_none(contract.inventory('meshes/unrelated.nif',b'bad',{})))
    before=contract.metadata()
    assert len(before['assets'])==2 and len(before['evidence'])==9 and before['contract']['sha256']==CONTRACT_SHA
    checks.append({'case':'all nine primary/evidence files hashed and only two paths granted','passed':True})
    for filename in ['legacy_nif_contracts.py','prepare_vfs_expectations.py','probe_resource_graph.py','probe_vfs_full.py']:
        ast.parse((OWN/filename).read_text('utf-8'),filename=filename)
    report={'status':'PASS_EXACT_SOURCE_FORMAT_PROOF_AND_NEGATIVE_GUARDS_NO_RUNTIME_PROBE',
            'checks':checks,'count':len(checks),'contract':before,'adapter_sha256':digest(OWN/'legacy_nif_contracts.py'),
            'limits':['No game/MO2/DLL execution or profile/resource mutation.','Actual injected winner/texture closure remains a mandatory final graph check.','Source format82 remains unrepaired and native rendering unverified.']}
    write_json(OWN/'legacy_nif_contract_verification_rev9.json',report)
    print(json.dumps({'status':report['status'],'checks':len(checks)},indent=2))


def assert_none(value):assert value is None


if __name__=='__main__':main()
