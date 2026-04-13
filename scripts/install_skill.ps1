param(
    [string]$TargetDir = "$HOME\.agents\skills\danxi-daily"
)

$ErrorActionPreference = "Stop"
$SourceDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir | Out-Null
}

Get-ChildItem -Path $SourceDir -Force | Where-Object {
    $_.Name -notin @('.git', 'outputs')
} | ForEach-Object {
    $dest = Join-Path $TargetDir $_.Name
    if (Test-Path $dest) {
        Remove-Item -Recurse -Force $dest
    }
    Copy-Item -Recurse -Force $_.FullName $dest
}

Write-Host "Installed danxi-daily skill to: $TargetDir"
