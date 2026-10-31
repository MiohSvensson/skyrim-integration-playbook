"""Source preflight and independent read-only after-check for the future FC patch."""
import argparse
import copy
import hashlib
import json
import struct
import sys
from datetime import datetime,timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent/'navmesh_patch'))
from verify_candidate import Plugin,geometry,navi_model,NAVI
sys.path.insert(0,str(OUT))
from analyze_navigation import View,cross_link_proof,PRIMARY,NEIGHBOR

PATCH='database forgotten city ussep navigation.esp'
CELL='skyrim.esm|007644'
WORLD='skyrim.esm|00003C'


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def uses_path(model,key):
    p=model['precomputed']
    return p is not None and (any(key in path for path in p['paths']) or any(x['navmesh']==key for x in p['roadmarkers']))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--vanilla',required=True)
    parser.add_argument('--feature',required=True)
    parser.add_argument('--ussep',required=True)
    parser.add_argument('--candidate')
    parser.add_argument('--navi-winning')
    parser.add_argument('--typed-log')
    parser.add_argument('--output',default=str(OUT/'source_preflight.json'))
    args=parser.parse_args()
    output=Path(args.output).resolve()
    assert output.is_relative_to(OUT.resolve()),'Reports must remain in this task directory'
    plan=json.loads((OUT/'comparison.json').read_text(encoding='utf-8'))
    paths={'vanilla':Path(args.vanilla),'feature':Path(args.feature),'USSEP':Path(args.ussep)}
    plugins={}
    for key,path in paths.items():
        assert sha(path)==plan['sources'][key]['sha256'],f'{key} differs from reviewed source file'
        plugins[key]=Plugin(path)
    report={'utc':datetime.now(timezone.utc).isoformat(),'status':'SOURCE_PREFLIGHT_PASS',
            'sources':{key:{'path':str(value.path),'sha256':sha(value.path)} for key,value in plugins.items()}}
    if args.candidate:
        assert args.navi_winning,'--navi-winning must be the builder-logged final prior source NAVI file'
        candidate=Plugin(args.candidate)
        assert candidate.name==PATCH,'Unexpected candidate filename'
        assert candidate.header_flags&0x200,'ESL flag absent'
        assert {'skyrim.esm','forgottencity.esp','unofficial skyrim special edition patch.esp'}.issubset(candidate.masters)
        records=[r for r in candidate.records if r['signature']!='TES4']
        assert sorted((r['signature'],r['id']) for r in records)==sorted([('NAVM',PRIMARY),('CELL',CELL),('NAVI',NAVI),('WRLD',WORLD)]),'Unexpected extra/new record'
        u=View(plugins['USSEP'],PRIMARY);a=View(plugins['vanilla'],PRIMARY)
        feature_neighbor=View(plugins['feature'],NEIGHBOR);old_neighbor=View(plugins['vanilla'],NEIGHBOR)
        actual=View(candidate,PRIMARY)
        expected_triangles=[list(t) for t in u.triangles]
        removed=plan['bounded_candidate_plan']['removed_USSEP_edge_index']
        assert removed==6
        for i,triangle in enumerate(u.triangles):
            for side in range(3):
                if triangle[6]&(1<<side):
                    value=triangle[3+side]
                    if value==removed:
                        assert i==50 and side==2
                        expected_triangles[i][3+side]=-1
                        expected_triangles[i][6]&=~(1<<side)
                    elif value>removed:expected_triangles[i][3+side]=value-1
        expected=copy.deepcopy(u.model)
        expected['triangles_sha256']=hashlib.sha256(b''.join(struct.pack('<hhh hhh HH',*t) for t in expected_triangles)).hexdigest()
        assert expected['triangles_sha256']==plan['bounded_candidate_plan']['expected_triangles_sha256']
        expected['edges']=[edge for i,edge in enumerate(u.model['edges']) if i!=removed]
        assert actual.model==expected,'Unexpected NVNM geometry/pathing/link/grid change'
        assert actual.triangles==expected_triangles,'Unexpected typed triangle tuple change'
        assert actual.vertices==u.vertices,'USSEP vertex bytes changed'
        semantic=[i for i in range(324) if actual.normalized(i)!=u.normalized(i)]
        assert semantic==[50],'Logical change extends beyond the single authored edge'
        proof=cross_link_proof(actual,feature_neighbor,a,old_neighbor)
        assert len(proof['USSEP_to_FC'])==len(proof['FC_to_USSEP'])==16
        for rows in proof.values():
            assert all(row['reciprocal_in_feature'] if 'reciprocal_in_feature' in row else row['reciprocal_in_base'] for row in rows)
            assert all(row['ordered_target_vertices_preserved'] for row in rows)
        for key in ('flags','vcs1','form_version','vcs2'):
            assert actual.record[key]==u.record[key],f'Unexpected NAVM header change: {key}'
        source=Plugin(args.navi_winning)
        assert source.path!=candidate.path and source.name!=PATCH,'Candidate cannot be its own source witness'
        original_record=source.get(NAVI,'NAVI')
        original=navi_model(source,original_record)
        desired=copy.deepcopy(original)
        actual_navi_record=candidate.get(NAVI,'NAVI')
        actual_navi=navi_model(candidate,actual_navi_record)
        feature_navi=navi_model(plugins['feature'],plugins['feature'].get(NAVI,'NAVI'))
        ussep_navi=navi_model(plugins['USSEP'],plugins['USSEP'].get(NAVI,'NAVI'))
        forwarded=[]
        for key in plan['seven_shared_NVMI_plan']:
            assert not uses_path(original,key),'Final NVPP uses a forwarded NAVM; requires separate investigation'
            assert key not in original['deleted_navmeshes'],'Final NAVI deletes a forwarded NAVM'
            chosen=ussep_navi if key==PRIMARY else feature_navi
            assert key in chosen['infos']
            desired['infos'][key]=copy.deepcopy(chosen['infos'][key])
            forwarded.append({'id':key,'source':'USSEP' if key==PRIMARY else 'ForgottenCity'})
        assert actual_navi==desired,'Unexpected NAVI change outside the seven exact selected NVMI entries'
        for key in ('flags','vcs1','form_version','vcs2'):
            assert actual_navi_record[key]==original_record[key],f'Unexpected NAVI header change: {key}'
        report['status']='BINARY_PASS_TYPED_RELOAD_REQUIRED'
        report['candidate']={'path':str(candidate.path),'sha256':sha(candidate.path),'records':records,
            'logical_changed_triangles':semantic,'retained_reciprocal_ports':[16,16],
            'NAVI_source':str(source.path),'NAVI_source_sha256':sha(source.path),'forwarded_NVMI':forwarded,
            'all_other_NVMI_NVPP_NVSI_preserved':True,'no_own_records':True}
        if args.typed_log:
            log=Path(args.typed_log);text=log.read_text(encoding='utf-8-sig',errors='replace')
            assert 'FC_NAV_RELOAD_TYPED_PASS|PORTS=16/16|OWN=0|NVMI=7' in text
            assert 'BOUNDED_NAVM_STOP:' not in text
            report['status']='STATIC_BINARY_AND_TYPED_RELOAD_PASS'
            report['typed_log']={'path':str(log.resolve()),'sha256':sha(log)}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(output)},ensure_ascii=False))


if __name__=='__main__':main()
