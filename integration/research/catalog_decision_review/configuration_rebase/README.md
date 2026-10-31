# Prepared private configuration rebase

`config_rebase_plan.json` is a prepared plan, not an application receipt. The two candidate INIs here are ordinary private files. No runtime destination, source provider, profile, original control file or shared database was modified by the authoring agent.

Root should apply only after its active producer/xEdit/MO2 session closes. Revalidate source SHAs, nlink and current profile resolution first. Back up the current private Game/ReShade.ini inside the plan's Database validation directory, then atomically replace it with the exact staged candidate. Create the new private CrashLogger.ini in the already enabled ZZ86 overlay, preserving the baseline provider unchanged. Verify both final profiles resolve this new overlay, then rehash all145 original controls and rerun the final configuration scan.

The plan includes before/candidate SHAs and nlink, UTF-8/BOM/CRLF details, exact old/new raw line hex, guarded preset dependency, backup path, directory creation list and current profile state. Only ReShade's preset/cache and CrashLogger's symbols/log directory values differ. The old ParallaxGen user settings and TexGen provenance remain preserved; final tools need fresh dedicated configuration.
