"""Classify exact observed path matches; never edit configuration winners."""
from pathlib import Path
import collections
import hashlib
import json

OUT=Path(__file__).resolve().parent


def main():
    source=OUT/'active_configuration_absolute_paths.json'
    raw=json.loads(source.read_text(encoding='utf-8'))
    rows=[]
    for row in raw['absolute_paths']:
        r=dict(row);scope=r['scope'];rel=r['relative'].replace('\\','/').casefold()
        if scope=='MO2':
            category='current_database_runtime_or_tool_path'
        elif scope in ('final-profile','build-profile') and rel=='skyrim.ini':
            category='screenshot_path_overridden_by_same_profile_SkyrimCustom'
        elif scope in ('final-profile','build-profile') and rel=='skyrimcustom.ini':
            category='current_database_runtime_or_tool_path'
        elif scope=='game-root' and rel=='reshade.ini':
            category='active_ReShade_stale_preset_or_cache_requires_private_relocation'
        elif rel=='skse/plugins/crashlogger.ini':
            category='active_CrashLogger_cache_requires_private_relocation'
        elif rel in ('cfg/user.json','pgpatcher/cfg/user.json'):
            category='old_offline_ParallaxGen_tool_settings_not_authorized_for_final_generation'
        elif rel=='textures/dyndolod/lod/texgen_sse.ini':
            category='old_TexGen_output_provenance_no_runtime_write_consumer_proven'
        elif rel=='skse/plugins/improvedcamerase/improvedcamerase.ini':
            category='system_font_dependency_not_working_cache'
        elif rel.startswith('skse/plugins/dynamicstringdistributor/') or rel.startswith('interface/translations/'):
            category='translated_text_roman_numeral_or_colon_newline_regex_false_positive'
        elif 'readme' in rel or rel=='sam/menu/spec.yaml' or rel.startswith('scripts/source/') or rel.endswith('cmakelists.txt'):
            category='documentation_comment_or_source_example'
        else:category='unclassified_requires_review'
        r['classification']=category;rows.append(r)
    unresolved=[r for r in rows if r['classification']=='unclassified_requires_review']
    assert not unresolved,unresolved
    report={'source_report':str(source),'source_report_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'counts':dict(collections.Counter(r['classification'] for r in rows)),'matches':rows,
            'additional_nonabsolute_setting':[{'provider':'T4459 Crash Logger SSE','relative':'SKSE/Plugins/CrashLogger.ini',
                'section':'Debug','key':'Crashlog Directory','value':'','reason':'Source comment declares default Documents/my games/[Skyrim]/SKSE; relocate output explicitly under Database as part of parent private overlay.'}],
            'recommended_parent_only_edits':[
                {'scope':'Game/ReShade.ini','section':'GENERAL','key':'IntermediateCachePath','target_relative_to_UnifiedSkyrim':'cache/reshade'},
                {'scope':'Game/ReShade.ini','section':'GENERAL','key':'PresetPath','target_relative_to_UnifiedSkyrim':'Game/LED REshade.ini'},
                {'scope':'winning SKSE/Plugins/CrashLogger.ini private overlay','section':'Debug','key':'Symcache Directory','target_relative_to_UnifiedSkyrim':'cache/crashlogger/symbols'},
                {'scope':'winning SKSE/Plugins/CrashLogger.ini private overlay','section':'Debug','key':'Crashlog Directory','target_relative_to_UnifiedSkyrim':'logs/crashlogger'}],
            'limits':'Exact text/source classification without executing game or configuration consumers. Offline-tool configs are retained evidence, not approved final generation settings. Parent owns actual private-file/overlay changes and final rescan.'}
    (OUT/'configuration_path_dispositions.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('All64 literal matches classified:',report['counts'])


if __name__=='__main__':main()
