# Source catalogue and adoption linkage review

The read-only snapshot accounts for all6495 original source mod directories: Anno1669, Burida2431 and TuLED2395. All sources and2269 materialized baseline directories exist. The52 equipment and14 feature plugins have selected physical files, are active in both current profiles, and link back to the correct source decisions and adopted directories. Source1666 retains both LOTD patch directory/reason entries. No disabled representative is still described as actively reused exact content.

The final-flag preview has these mutually exclusive source decisions:

| Decision | Sources |
|---|---:|
| Enabled baseline source |2264|
| Exact original-content duplicate |2001|
| Originally disabled, retained in catalogue |458|
| Source alternative retained, not adopted |1721|
| Standalone feature resource adoption |12|
| Explicit files partially adopted |32|
| Optional mismatched add-on source disabled |5|
| Exact duplicate of an explicitly disabled source |2|
| Total |6495|

`catalogue_logic_and_linkage.json` records the catalogue generator SHA, current profile-control SHAs, every baseline directory and66 plugin linkages. It found zero missing sources, zero physical adoption-linkage issues and zero inactive exact representatives. The Build profile intentionally excludes the old Synthesis and DynDOLOD generation layers while the final profile still contains them pending replacement; this temporary producer context is separately documented.

The shared CSV/DB has now been refreshed **without** `--final`; the follow-up read-only audit reports zero decision/directory differences from current logic and zero linkage issues. The1721 remaining source alternatives are still work-in-progress, not finalized rejections. Only run the writer with `--final` after final generation/validation. The1721 figure replaces the earlier1765 figure because44 original sources received explicit standalone/partial adoption decisions.

Catalogue completeness does not mean every original source is active or that every source was merged. Category regexes are triage, not translated-name identity evidence. Whole-tree SHA identity excludes root meta.ini and describes original content, not winning overlays. A source directory may contain disabled optional plugins or files superseded by verified repairs. Source-declared version metadata can differ from plugin content: LOTD directories labelled6.10 contain the independently compared6.7.2 plugin. New generated and repair layers require their separate final runtime inventory.

The physical layout uses journaled NTFS hardlinks for immutable assets and private copies for writable/plugin inputs, with no baseline directory junctions. File-level checks, native diagnostic checks and final normal-schema reloads remain distinct from game runtime testing; this review never launches the game. `audit_catalog.py` opens both databases read-only and writes only this research directory.

The optional configuration pass scanned15113 current physical loose winners and35 additional Game/profile/MO2 text configurations,265103669 bytes total, with zero read errors and an unchanged final modlist. The64 absolute-path-like matches are fully classified in `configuration_path_dispositions.json`. No exact original three-pack installation prefix remains. Three live settings still need parent relocation: ReShade preset and effect cache, plus CrashLogger symbol cache; CrashLogger's empty log directory also defaults outside Database. The two old screenshot values are overridden by same-profile SkyrimCustom.ini values under Database. Six ParallaxGen paths and one TexGen output path describe old offline-tool configuration/provenance and cannot be used for final generation as-is. Documentation paths, Windows font dependencies and translation false matches are identified separately. This is physical-priority resolution, not an injected VFS probe, and later profile/configuration changes require a final refresh.
