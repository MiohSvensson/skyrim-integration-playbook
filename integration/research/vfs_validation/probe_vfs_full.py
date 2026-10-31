"""Run both read-only VFS phases and preserve their separate evidence files."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
from vfs_common import OWN,safe_output,write_json,injected


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--expect',required=True);p.add_argument('--output',required=True);p.add_argument('--all-paths',action='store_true')
    a=p.parse_args();output=safe_output(a.output);phase1=output.with_name(output.stem+'_files.json');phase2=output.with_name(output.stem+'_graph.json')
    command=[sys.executable,str(OWN/'probe_vfs.py'),'--data',a.data,'--expect',a.expect,'--output',str(phase1)]
    if a.all_paths:command.append('--all-paths')
    one=subprocess.run(command).returncode
    command=[sys.executable,str(OWN/'probe_resource_graph.py'),'--data',a.data,'--expect',a.expect,'--output',str(phase2),'--seed-probe',str(phase1)]
    two=subprocess.run(command).returncode
    first=json.loads(phase1.read_text(encoding='utf-8')) if phase1.exists() else {'errors':[{'kind':'file_probe_did_not_write_result'}]}
    second=json.loads(phase2.read_text(encoding='utf-8')) if phase2.exists() else {'errors':[{'kind':'graph_probe_did_not_write_result'}]}
    limited=bool(second.get('optional_missing_source_morphs') or second.get('optional_missing_hkx_extension_slots') or second.get('documented_feature_source_limitations') or second.get('documented_legacy_nif_formats'))
    status='FAIL' if one or two or first['errors'] or second['errors'] else 'PARTIAL_ALL_PATHS_NOT_RUN' if not a.all_paths else 'PASS_STATIC_VFS_WITH_DOCUMENTED_SOURCE_LIMITATIONS' if limited else 'PASS_STATIC_VFS_AND_RESOURCE_GRAPH'
    report={'status':status,'usvfs_x64_injected':injected(),'data_path':a.data,'expectations':a.expect,'file_probe':str(phase1),'graph_probe':str(phase2),
      'file_probe_errors':len(first['errors']),'graph_probe_errors':len(second['errors']),
      'all_runtime_paths':first.get('checks',{}).get('all_runtime_paths'),'graph_counts':second.get('counts'),
      'documented_feature_source_limitations':second.get('documented_feature_source_limitations',[]),
      'documented_legacy_nif_formats':second.get('documented_legacy_nif_formats',[]),
      'limitations':second.get('limitations',[])}
    write_json(output,report);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True);return 2 if status=='FAIL' else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
