"""Audit all intended Persistent-bit moves and every current seed group context."""
import collections
import hashlib
import json
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT, scan


def placement(r):
    groups=r['groups']
    cells=[label for kind,label in groups if kind==6]
    worlds=[label for kind,label in groups if kind==1]
    child=[kind for kind,label in groups if kind in (8,9,10)]
    return {'cell':cells[-1] if cells else None,'world':worlds[-1] if worlds else None,
            'child_group_type':child[-1] if child else None,'groups':groups}


def main():
    plan=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    guards={g['filename'].casefold():g for g in plan['input_file_guards']}
    by_path=collections.defaultdict(set)
    for r in plan['priority_seed_records']:
        key=(r['origin'],int(r['object_id'],16));by_path[r['base_path']].add(key)
        if r['persistent']:
            for n in r['donors']:by_path[guards[n.casefold()]['path']].add(key)
    parsed={path:scan(path,wanted=keys)[0] for path,keys in by_path.items()}
    seeds={(r['origin'],int(r['object_id'],16)):r for r in plan['priority_seed_records']}
    moves=[];contexts=[]
    for s in plan['priority_seed_records']:
        key=(s['origin'],int(s['object_id'],16));base=parsed[s['base_path']][key]
        b=placement(base)
        contexts.append({'record':f'{key[0]}|{key[1]:06X}','provider':s['base_file'],'signature':s['signature'],
                         'persistent_change':s['persistent'],'base_placement':b})
        if not s['persistent']:continue
        assert base['signature'] in ('REFR','ACHR')
        assert b['cell'] is not None and b['child_group_type'] in (8,9,10)
        donor=[]
        for n in s['donors']:
            r=parsed[guards[n.casefold()]['path']][key]
            d=placement(r)
            if r['flags']&0x400:
                assert d['child_group_type']==8,(key,n,d)
                assert d['world']==b['world'],(key,n,'author changed world',b,d)
                donor.append({'provider':n,'placement':d})
        assert donor,(key,'no exact authored persistent placement')
        targets={tuple(d['placement']['cell']) for d in donor};assert len(targets)==1
        target=next(iter(targets))
        if b['world'] is None:assert target==tuple(b['cell']),(key,'interior cell moved')
        seed=seeds.get(target)
        moves.append({'record':f'{key[0]}|{key[1]:06X}','signature':base['signature'],'base_file':s['base_file'],
             'base_path':s['base_path'],'source_placement':b,'authored_donors':donor,
             'expected_target_cell':target,'expected_target_world':b['world'],'expected_child_group_type':8,
             'target_cell_explicitly_seeded':seed is not None,'target_cell_seed':seed,
             'base_DATA_hex':next(v.hex() for t,v in base['fields'] if t=='DATA')})
    result={'persistent_moves':moves,'base_seed_contexts':contexts,'new_missing_explicit_cell_seeds':[r['expected_target_cell'] for r in moves if not r['target_cell_explicitly_seeded']],
            'primary_sources':[
                {'path':str(OUT/'source_4_1_5f/wbImplementation.pas'),'lines':[13173,13185],'fact':'SetIsPersistent updates the header and calls UpdateCellChildGroup.'},
                {'path':str(OUT/'source_4_1_5f/wbImplementation.pas'),'lines':[13457,13576],'fact':'Persistent exterior references move to the same WRLD persistent CELL; interiors keep their CELL. Physical group changes to type8.'},
                {'path':str(OUT/'source_4_1_5f/wbImplementation.pas'),'lines':[23792,23881],'fact':'Synthetic ContainedIn Cell is regenerated from actual group label and explicitly dcfDontSave.'},
                {'path':str(OUT/'source_4_1_5f/wbImplementation.pas'),'lines':[24552,24556],'fact':'The synthetic element for Cell Children group6 is a FormID definition named Cell.'}]}
    (OUT/'persistent_placement_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Persistent plans:',len(moves),'explicit target cells:',all(r['target_cell_explicitly_seeded'] for r in moves))
    for r in moves:print(r['record'],r['source_placement']['cell'],'=>',r['expected_target_cell'],'world',r['expected_target_world'],'seed',r['target_cell_explicitly_seeded'])


if __name__=='__main__':main()
