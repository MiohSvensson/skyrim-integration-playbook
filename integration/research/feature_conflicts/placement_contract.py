"""Frozen physical-GRUP expectations; only the 18 authored Persistent moves vary."""
import collections
import struct

from analyze_fields import scan


def encode_groups(groups):
    result=[]
    for kind,label in groups:
        if isinstance(label,(tuple,list)):
            label=f'{label[0].casefold()}|{int(label[1]):06X}'
        elif kind==0:label=struct.pack('<I',label).decode('ascii')
        result.append([kind,label])
    return result


def describe(groups):
    cell=next((tuple(label) for kind,label in reversed(groups) if kind==6),None)
    world=next((tuple(label) for kind,label in reversed(groups) if kind==1),None)
    kind=next((kind for kind,label in reversed(groups) if kind in (8,9,10)),None)
    return cell,world,kind


def build(priority,quest):
    rows={};sources={};paths=collections.defaultdict(set)
    guards={g['filename'].casefold():g for g in priority['input_file_guards']+quest['input_file_guards']}
    for row in priority['priority_seed_records']:
        key=(row['origin'],int(row['object_id'],16));sources[key]=(row['base_path'],row['base_file'])
        paths[row['base_path']].add(key)
    for row in quest['rows']:
        key=(row['origin'],int(row['object_id'],16))
        if key in sources:assert sources[key][0]==row['seed_path'],('Different shared seed provider',key)
        sources[key]=(row['seed_path'],row['seed_file']);paths[row['seed_path']].add(key)
    for row in priority['priority_seed_records']:
        if row['persistent']:
            for name in row['donors']:paths[guards[name.casefold()]['path']].add((row['origin'],int(row['object_id'],16)))
    parsed={path:scan(path,wanted=keys)[0] for path,keys in paths.items()}
    changes={(r['origin'],int(r['object_id'],16)):r for r in priority['priority_seed_records'] if r['persistent']}
    for key,(path,provider) in sources.items():
        record=parsed[path][key];groups=record['groups'];cell,world,kind=describe(groups)
        expected=groups;target=cell;target_kind=kind;persistent=key in changes
        if persistent:
            targets=set()
            for name in changes[key]['donors']:
                donor=parsed[guards[name.casefold()]['path']][key]
                if not donor['flags']&0x400:continue
                dcell,dworld,dkind=describe(donor['groups'])
                assert dworld==world and dkind==8
                targets.add(dcell)
            assert len(targets)==1,(key,targets)
            target=next(iter(targets));target_kind=8
            assert target in sources,('Persistent target CELL was not explicitly seeded',key,target)
            target_path,_=sources[target];target_record=parsed[target_path][target]
            assert target_record['signature']=='CELL'
            if world is None:assert target==cell
            else:
                assert target_record['flags']&0x400,('Exterior target is not persistent CELL',key,target)
                assert describe(target_record['groups'])[1]==world
            expected=target_record['groups']+[(6,target),(8,target)]
        row={'record':f'{key[0]}|{key[1]:06X}','origin':key[0],'object_id':f'{key[1]:06X}',
             'source_path':path,'source_provider':provider,'signature':record['signature'],
             'source_groups':encode_groups(groups),'expected_groups':encode_groups(expected),'persistent_change':persistent}
        if record['signature'] in ('REFR','ACHR'):
            assert cell is not None and kind in (8,9,10)
            row|={'source_cell':list(cell),'target_cell':list(target),'world':list(world) if world else None,
                  'source_child_group_type':kind,'expected_child_group_type':target_kind,
                  'source_DATA_hex':next(v.hex() for t,v in record['fields'] if t=='DATA')}
        rows[row['record']]=row
    return {'rows':rows,'persistent_changes':len(changes),
            'rule':'Every output record preserves physical canonical GRUP ancestry. Only18 explicit persistent REFR/ACHR targets move to the exact same-WRLD authored persistent CELL and type8 group; interior CELL remains unchanged. Source DATA bytes stay exact.'}


def pascal_dispatch(contract,quote):
    lines=[]
    for row in sorted(contract['rows'].values(),key=lambda r:r['record']):
        if row['signature'] not in ('REFR','ACHR'):continue
        sc,tc,world=row['source_cell'],row['target_cell'],row['world']
        lines.append(f"  if SameText(origin, {quote(row['origin'])}) and (id = ${row['object_id']}) then begin")
        lines.append(f"    Need(persistent = {row['persistent_change']}, 'Unplanned Persistent policy at {row['record']}');")
        lines.append(f"    AssertReferencePlacement(base, dst, {quote(sc[0])}, ${sc[1]:06X}, {quote(tc[0])}, ${tc[1]:06X}, "+
                     f"{quote(world[0]) if world else quote('')}, ${world[1] if world else 0:06X}, {row['source_child_group_type']}, {row['expected_child_group_type']});")
        lines.append('    matched := True;\n  end;')
    return '\n'.join(lines)


def check_physical_groups(record,expected):
    actual=encode_groups(record['groups'])
    issues=[]
    if actual!=expected['expected_groups']:
        issues.append({'reason':'Physical canonical GRUP ancestry differs','expected':expected['expected_groups'],'actual':actual})
    if record['signature'] in ('REFR','ACHR') and 'source_DATA_hex' in expected:
        data=[v.hex() for t,v in record['fields'] if t=='DATA']
        if data!=[expected['source_DATA_hex']]:issues.append({'reason':'Reference DATA coordinates/rotation bytes changed','expected':expected['source_DATA_hex'],'actual':data})
    return issues
