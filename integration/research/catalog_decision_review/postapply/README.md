# Independent post-application verification

`configuration_rebase_postapply_verified.json` records a read-only PASS for the current applied state. All four INI values match the reviewed staged candidates. Game/ReShade.ini and the new private ZZ86 CrashLogger.ini have nlink1, exact expected SHAs and only the two declared raw-line changes each; their BOM/line endings and other bytes match the original source or guarded backup.

Both current profiles resolve CrashLogger.ini to ZZ86. Root journal row491431 points to the private ReShade candidate with matching destination SHA, size and mtime. The original ReShade and CrashLogger mod files, materialized T4459 provider and all145 original control files retain their expected hashes. All planned cache/log/backup directories exist.

The final profile scan covers15113 winning data configurations plus35 Game/profile/MO2 files; the Build scan covers15086 plus35. Both scans have zero read errors and unchanged modlists. All65 absolute-path-like matches are classified; ReShade's two and CrashLogger's two paths now point inside Database. The original three named pack prefixes have zero matches. Six preserved old ParallaxGen paths, one TexGen provenance path, two overridden screenshot values, Windows fonts and documentation/translation examples remain explicitly identified.

This proves current physical profile priority and file integrity. It does not replay or independently prove the earlier application/rollback history, inject a VFS probe, execute consumers, or launch the game. Later configuration/profile changes require another final refresh. Initial pre-application reports remain preserved outside this postapply directory.
