param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Anno','Burida','TuLED')]
    [string]$Pack,
    [switch]$DryRun
)
$taskScript = Join-Path $PSScriptRoot 'rootcause\launch_verified_xedit.py'
$taskArguments = @($taskScript, $Pack)
if ($DryRun) { $taskArguments += '--dry-run' }
& python @taskArguments
exit $LASTEXITCODE
