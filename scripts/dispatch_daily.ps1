param(
    [string]$Repo = "0patsick0/danxi-daily-skill",
    [string]$Workflow = "DanXi Daily Auto Post",
    [string]$Ref = "main",
    [switch]$DryRun,
    [switch]$OnlyIfMissed
)

$ErrorActionPreference = "Stop"

function Get-ChinaTodayStamp {
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("China Standard Time")
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $tz).ToString("yyyyMMdd")
}

function Get-PostedSlot {
    param([string]$RepoName)
    try {
        $encoded = gh api "repos/$RepoName/contents/outputs/last_post_slot.txt" --jq ".content" 2>$null
    } catch {
        return ""
    }
    if ([string]::IsNullOrWhiteSpace($encoded)) {
        return ""
    }
    $normalized = ($encoded -replace "\s", "")
    try {
        return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($normalized)).Trim()
    } catch {
        return ""
    }
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw "GitHub CLI (gh) is not on PATH. Install it from https://cli.github.com/ and run 'gh auth login'."
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$stamp] dispatch_daily start repo=$Repo dry_run=$DryRun only_if_missed=$OnlyIfMissed"

if ($OnlyIfMissed -and -not $DryRun) {
    $today = Get-ChinaTodayStamp
    $slot = Get-PostedSlot -RepoName $Repo
    if ($slot -eq $today -or $slot.StartsWith("$today-")) {
        Write-Output "[$stamp] already posted today (slot=$slot); skipping dispatch."
        exit 0
    }
    Write-Output "[$stamp] no post slot for $today (last=$slot); dispatching."
}

$ghArgs = @(
    "workflow", "run", $Workflow,
    "--repo", $Repo,
    "--ref", $Ref
)
if ($DryRun) {
    $ghArgs += @("-f", "dry_run=true")
}

Write-Output "[$stamp] Dispatching '$Workflow' on $Repo@$Ref ..."
& $gh.Source @ghArgs
if ($LASTEXITCODE -ne 0) {
    throw "gh workflow run failed with exit code $LASTEXITCODE"
}

Write-Output "[$stamp] Dispatched. Check: https://github.com/$Repo/actions"
