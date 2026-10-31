"""Prove both original referents absent; preserve the exact source nil parent.

The all-signature complete active-header scan and all16 actual native source
nodes are audited before changing four research authoring guards. No invented
CELL, input mutation, dispatched-script edit, or general nil allowance.
"""
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[3]


def pin(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def parse_node(line):
    keys='depth|name|base|definition|element|children|nativeVarType|native|edit|record|links|path'
    matches=list(re.finditer(r'\|('+keys+r')=',line));out={}
    for i,m in enumerate(matches):out[m.group(1)]=line[m.end():matches[i+1].start() if i+1<len(matches) else len(line)]
    return out


def main():
    task=BASE/'UnifiedSkyrim/validation/fc_navigation_v5'
    inventory_path=task/'input_inventory.json';inputs=json.loads(inventory_path.read_text('utf-8'))['plugins']
    hits=[];records=0;started=time.monotonic()
    for row in inputs:
        data=Path(row['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256']
        masters=[n.casefold() for n in row['masters']];pos=0
        while pos<len(data):
            assert pos+24<=len(data)
            sig=data[pos:pos+4];n,flags,fid=struct.unpack_from('<III',data,pos+4)
            if sig==b'GRUP':assert n>=24 and pos+n<=len(data);pos+=24;continue
            assert pos+24+n<=len(data);records+=1;index=fid>>24
            if index<=len(masters):
                owner=masters[index] if index<len(masters) else row['name'].casefold()
                if owner=='skyrim.esm' and fid&0xFFFFFF in (0x28E34,0x28E37):
                    hits.append({'plugin':row['name'],'signature':sig.decode('ascii'),'raw_form_id':f'{fid:08X}','flags':flags})
            pos+=24+n
    assert hits==[],('Do not assume source parent absence',hits)
    log_path=task/'logs/xedit.log';log=log_path.read_text('utf-8-sig');result=json.loads((task/'result.json').read_text('utf-8'))
    assert result['log_sha256']==pin(log_path)['sha256'] and result['usvfs'] and result['changed_input_plugins']==[]
    nodes=[parse_node(l) for l in log.splitlines() if l.startswith('NAVMI_ORPHAN_TREE|')]
    expected=[('NVMI - Navmesh Info',17,3,12,0),('Navmesh',10,9,0,19),('Category',10,9,0,19),
              ('X',14,9,0,5),('Y',14,9,0,5),('Z',14,9,0,5),('Preferred Merges Flag',8,9,0,8209),
              ('Edge Links',16,7,0,0),('Preferred Edge Links',16,7,0,0),('Door Links',16,7,0,0),
              ('Is Island',10,9,0,17),('Island',18,12,0,8209),('PathingCell',17,8,3,0),
              ('CRC Hash',10,9,0,19),('Parent Worldspace',10,9,0,19),('Parent',18,12,0,19)]
    assert len(nodes)==len(expected)==16 and 'NAVMI_ORPHAN_TREE_COMPLETE|NODES=16' in log
    for n,e in zip(nodes,expected):
        assert (n['base'],int(n['definition']),int(n['element']),int(n['children']),int(n['nativeVarType']))==e,(n,e)
        assert n['record']=='skyrim.esm|012FB4' and n['links']=='<none>'
    by_name={r['base']:r for r in nodes}
    for name,value in [('Navmesh',0x28E37),('Category',0),('Is Island',0),('CRC Hash',0xA5E9A03C),('Parent Worldspace',0),('Parent',0x28E34)]:
        assert int(by_name[name]['native'])==value
    assert by_name['Preferred Merges Flag']['native']=='00 00 00 00'
    for name,bits in [('X','A0FD53C5'),('Y','25E18E43'),('Z','4E176F43')]:
        line=next(l for l in log.splitlines() if l.startswith('NAVMI_ORPHAN_FLOAT_SINGLE|'+name+'|'))
        assert '|actualLE='+bits+'|literalLE='+bits+'|expectedLE='+bits in line
    proof={'status':'ALL_SIGNATURE_BOTH_SOURCE_REFERENTS_ABSENT_AND_ALL16_NATIVE_NODES_AUDITED',
           'input_inventory':pin(inventory_path),'plugins':len(inputs),'records_all_signatures':records,
           'all_input_plugin_SHA_verified':True,'identities':['skyrim.esm|028E34','skyrim.esm|028E37'],
           'record_hits_of_any_signature':hits,'native_log':pin(log_path),'native_nodes':nodes,
           'all_remaining_v5_guard_assumptions':'All exact schema/count/scalar/merge/empty-array/float-bit/world/raw-parent checks agree with full native dump and passed before final assigned-parent assertion. Only the imagined resolved parent-CELL assertion was wrong.',
           'seconds':round(time.monotonic()-started,3)}
    proof_path=OWN/'stock_orphan_parent_absence_v6.json';proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    prior_path=OWN/'stock_orphan_lookup_fix_manifest_v5.json';prior=json.loads(prior_path.read_text('utf-8'))
    archive=OWN/'frozen/stock_orphan_v5_before_v6';assert not archive.exists();archive.mkdir(parents=True)
    (archive/(prior_path.name+'.frozen.txt')).write_bytes(prior_path.read_bytes())
    rows=[];diffs=[]
    for row in prior['files']:
        path=Path(row['after']['path']);assert pin(path)['sha256']==row['after']['sha256']
        old=path.read_text('utf-8');copy=archive/(path.name+'.frozen.txt');copy.write_bytes(path.read_bytes())
        new=old.replace('parentElement, parentCell: IInterface;','parentElement: IInterface;',1)
        start=new.index('  parentCell := LinksTo(parentElement);')
        end=new.index("  AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_FULL_TYPED_GUARD_PASS",start)
        replacement="""  // Both original scalar referents028E37(NAVM) and028E34(parent CELL)
  // are absent in the complete SHA-frozen active record index, all signatures.
  // Preserve this exact source nil; never invent a parent or change its bytes.
  Need(not Assigned(LinksTo(parentElement)),
    'Known stock orphan parent unexpectedly resolves; re-audit' + StockFieldContext(parentElement, 'exact00028E34 / nil link'));
"""
        new=new[:start]+replacement+new[end:]
        assert 'parentCell :=' not in new
        for a,b in [('procedure AssertNativeByteVector','procedure AssertTree'),('function StockSingleLE','function IsKnownStockOrphan')]:
            assert old[old.index(a):old.index(b)]==new[new.index(a):new.index(b)]
        path.write_text(new,encoding='utf-8',newline='\n')
        rows.append({'before':row['after'],'frozen_before':pin(copy),'after':pin(path)})
        diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(copy),tofile=str(path)))
    for x,y in [(rows[0],rows[1]),(rows[2],rows[3])]:
        a=Path(x['after']['path']).read_text('utf-8');b=Path(y['after']['path']).read_text('utf-8');assert a.replace('VERIFY_ONLY = False;','VERIFY_ONLY = True;',1)==b
    diff=OWN/'stock_orphan_parent_absence_v6.diff';diff.write_text(''.join(diffs),encoding='utf-8',newline='\n')
    report={'schema':'skyrim.bounded_navi_orphan_lookup_fix.v4','revision':6,'utc':datetime.now(timezone.utc).isoformat(),
            'status':'AUTHORING_V6_EXACT_SOURCE_NIL_PARENT_NATIVE_EXECUTION_PENDING','previous_manifest':pin(prior_path),
            'complete_parent_absence_and_native_guard_audit':pin(proof_path),'files':rows,'diff':pin(diff),'patcher':pin(__file__),
            'changes':['Exact raw parent00028E34 remains dtUnion/etUnion/zero-child scalar, but must have nilLinksTo as independently proved across every active record signature.','No placeholder CELL/NAVM, source changes, new missing-key categories, or broad nil skips. Sole original source NVMI key028E37 stays a lookup/classification-only allowance.','Full12field/49byte reconstruction, original stockSHA/actualVFSCRC, complete first-call16node diagnostics, all3 strict Single-byte witnesses, duplicate/target checks and full nontarget NAVI binary/typed preservation retained.'],
            'limits':['Native v6 run, independent candidate binary check and fresh installed typed reload still mandatory.','No runtime/profile/dispatchedv5/rev9 change.']}
    manifest=OWN/'stock_orphan_lookup_fix_manifest_v6.json';manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    frozen=OWN/'frozen/stock_orphan_v6';frozen.mkdir(parents=True);items=[]
    for p in [Path(r['after']['path']) for r in rows]+[manifest,proof_path,Path(__file__)]:
        c=frozen/(p.name+'.frozen.txt');c.write_bytes(p.read_bytes());items.append(pin(p)|{'frozen_source_copy':str(c)})
    index=OWN/'stock_orphan_v6_tools_frozen.json';index.write_text(json.dumps({'status':report['status'],'files':items},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'proof':pin(proof_path),'manifest':pin(manifest),'freeze':pin(index),'records':records,'hits':hits},indent=2))


if __name__=='__main__':main()
