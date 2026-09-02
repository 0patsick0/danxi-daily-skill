param(
    [string]$Repo = "0patsick0/danxi-daily-skill",
    [string]$Workflow = "DanXi Daily Auto Post",
    [string]$Ref = "main",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw "GitHub CLI (gh) is not on PATH. Install it from https://cli.github.com/ and run 'gh auth login'."
}

$args = @(
    "workflow", "run", $Workflow,
    "--repo", $Repo,
    "--ref", $Ref
)
if ($DryRun) {
    $args += @("-f", "dry_run=true")
}

Write-Output "Dispatching '$Workflow' on $Repo@$Ref ..."
& $gh.Source @args
if ($LASTEXITCODE -ne 0) {
    throw "gh workflow run failed with exit code $LASTEXITCODE"
}

Write-Output "Dispatched. Check: https://github.com/$Repo/actions"
