"""Shared exact source/visible-parent scope for read-only comparator preflight."""
import collections
import json
from pathlib import Path

from analyze_fields import OUT, scan


def scope(priority, quest):
    guards={}
    for g in priority['input_file_guards']+quest['input_file_guards']:
        key=g['filename'].casefold()
        if key in guards:assert guards[key]['sha256']==g['sha256'],key
        else:guards[key]=g
    exact={}
    def add(name, origin, object_id, role):
        key=(name.casefold(),origin.casefold(),int(object_id,16) if isinstance(object_id,str) else object_id)
        exact.setdefault(key,{'provider':name,'origin':key[1],'object_id':f'{key[2]:06X}','roles':[]})['roles'].append(role)
    for r in priority['priority_seed_records']:add(r['base_file'],r['origin'],r['object_id'],'priority base')
    for r in priority['typed_field_operations']:
        origin,object_id=r['record'].split('|');add(r['source'],origin,object_id,'typed-field donor')
    for r in quest['rows']:
        add(r['seed_file'],r['origin'],r['object_id'],'quest seed')
        if r['field_source']:add(r['field_source'],r['origin'],r['object_id'],'quest typed-field donor')
    add('SofiaFollower.esp','sofiafollower.esp',0xAA58,'complete source quest')
    add('SofiaFollower.esp','skyrim.esm',0x9845C,'complete source clone PACK')
    paths=collections.defaultdict(set)
    for name,origin,obj in exact:paths[guards[name]['path']].add((origin,obj))
    parents={}
    for path,keys in paths.items():
        records=scan(path,wanted=keys)[0]
        assert set(records)==keys,(path,keys-set(records))
        name=Path(path).name
        for key,r in records.items():
            for group_type,label in r['groups']:
                if group_type not in (1,6,7):continue
                origin,obj=label
                pkey=(name.casefold(),origin.casefold(),obj)
                parents.setdefault(pkey,{'context_provider':name,'origin':origin.casefold(),'object_id':f'{obj:06X}',
                    'group_types':set(),'rule':'Resolve exactly as visible for this source file; master parent fallback is valid and actual provider is logged.'})['group_types'].add(group_type)
    for r in parents.values():r['group_types']=sorted(r['group_types'])
    return {'input_file_guards':sorted(guards.values(),key=lambda g:g['filename'].casefold()),
            'exact_records':sorted(exact.values(),key=lambda r:(r['provider'].casefold(),r['origin'],r['object_id'])),
            'visible_source_parents':sorted(parents.values(),key=lambda r:(r['context_provider'].casefold(),r['origin'],r['object_id']))}


def statements(rows, quote):
    lines=[]
    for r in rows['exact_records']:
        lines.append(f"    AuditExactSource({quote(r['provider'])}, {quote(r['origin'])}, ${r['object_id']});")
    for r in rows['visible_source_parents']:
        lines.append(f"    AuditVisibleSourceParent({quote(r['context_provider'])}, {quote(r['origin'])}, ${r['object_id']});")
    return '\n'.join(lines)


def current_scope(priority=None, quest=None):
    priority=priority or json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    quest=quest or json.loads((OUT/'quest_extension_plan.json').read_text(encoding='utf-8'))
    return scope(priority,quest)
