param(
    [string]$TaskName = "DanXiDailyReport",
    [string]$Time = "08:00",
    [string[]]$CatchUpTimes = @(),
    [switch]$EnablePost,
    [switch]$DispatchGitHub,
    [string]$Repo = "0patsick0/danxi-daily-skill",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Key
    )

    if (-not (Test-Path $Path)) {
        return ""
    }

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*=\s*(.*)\s*$"
    foreach ($line in Get-Content -Path $Path) {
        if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line -match $pattern) {
            $value = $Matches[1].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                return $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return ""
}

function Quote-PowerShellLiteral {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Assert-Hhmm {
    param([string]$Value)
    if ($Value -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') {
        throw "Time must be HH:MM in 24-hour format: $Value"
    }
}

$CatchUpTimes = @(
    $CatchUpTimes |
        ForEach-Object { $_ -split "," } |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ }
)

Assert-Hhmm -Value $Time
foreach ($catchUp in $CatchUpTimes) {
    Assert-Hhmm -Value $catchUp
}

function New-DailyTriggers {
    param([string[]]$Times)
    $unique = $Times | Where-Object { $_ } | Select-Object -Unique
    return @($unique | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
}

function New-ReliableSettings {
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -DontStopOnIdleEnd `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    try {
        $settings.WakeToRun = $true
    } catch {
        # Older Windows builds may not expose WakeToRun; StartWhenAvailable still helps.
    }
    return $settings
}

$runScript = Join-Path $ProjectRoot "scripts\run_daily.ps1"
$dispatchScript = Join-Path $ProjectRoot "scripts\dispatch_daily.ps1"
$logFile = Join-Path $ProjectRoot "outputs\cron.log"
$envFile = Join-Path $ProjectRoot ".env"

if ($DispatchGitHub) {
    if (-not (Test-Path $dispatchScript)) {
        throw "dispatch_daily.ps1 not found at $dispatchScript"
    }
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        throw "GitHub CLI (gh) is not on PATH. Install it from https://cli.github.com/ and run 'gh auth login'."
    }

    $escapedDispatch = Quote-PowerShellLiteral $dispatchScript
    $escapedRepo = Quote-PowerShellLiteral $Repo
    $escapedLogFile = Quote-PowerShellLiteral $logFile
    $escapedGhDir = Quote-PowerShellLiteral (Split-Path -Parent $gh.Source)
    $command = "`$env:Path = $escapedGhDir + [IO.Path]::PathSeparator + `$env:Path; & $escapedDispatch -Repo $escapedRepo -OnlyIfMissed *>> $escapedLogFile"

    $times = @($Time) + @($CatchUpTimes)
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command $command" -WorkingDirectory $ProjectRoot
    $triggers = New-DailyTriggers -Times $times
    $settings = New-ReliableSettings
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description "Dispatch DanXi daily GitHub Actions workflow if today's post is missing" -Force | Out-Null

    Write-Output "Scheduled task '$TaskName' registered at $($times -join ', ')."
    Write-Output "Mode: GitHub Actions workflow_dispatch (does not depend on GitHub native cron)."
    Write-Output "Guard: -OnlyIfMissed (skips if outputs/last_post_slot.txt is already today's date)."
    Write-Output "Repo: $Repo"
    Write-Output "Logs: $logFile"
    Write-Output "Runs as $env:USERNAME when that account is logged on. If the PC is asleep, Windows will try to run it when available."
    Write-Output "If this PC is powered off every evening, add a cloud cron as well (see docs/scheduling.md)."
    return
}

if (-not (Test-Path $runScript)) {
    throw "run_daily.ps1 not found at $runScript"
}

$arguments = @(
    "--hours", "24",
    "--top", "12",
    "--webvpn-mode", "auto",
    "--webvpn-no-prompt"
)

if ($EnablePost) {
    $postEndpoint = $env:DANXI_POST_ENDPOINT
    if ([string]::IsNullOrWhiteSpace($postEndpoint)) {
        $postEndpoint = Get-DotEnvValue -Path $envFile -Key "DANXI_POST_ENDPOINT"
    }

    $postToken = $env:DANXI_POST_TOKEN
    if ([string]::IsNullOrWhiteSpace($postToken)) {
        $postToken = Get-DotEnvValue -Path $envFile -Key "DANXI_POST_TOKEN"
    }

    if ([string]::IsNullOrWhiteSpace($postEndpoint) -or [string]::IsNullOrWhiteSpace($postToken)) {
        throw "-EnablePost requires DANXI_POST_ENDPOINT and DANXI_POST_TOKEN in environment or .env"
    }

    $arguments += @("--post", "--post-endpoint", $postEndpoint, "--post-at", $Time)
}

$escapedArgs = $arguments | ForEach-Object { Quote-PowerShellLiteral $_ }
$escapedRunScript = Quote-PowerShellLiteral $runScript
$escapedLogFile = Quote-PowerShellLiteral $logFile
$command = "& $escapedRunScript $($escapedArgs -join ' ') *>> $escapedLogFile"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command $command" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Generate DanXi daily report" -Force | Out-Null

Write-Output "Scheduled task '$TaskName' registered at $Time."
if ($EnablePost) {
    Write-Output "Posting mode enabled with post window at $Time."
} else {
    Write-Output "Posting mode disabled (generate only)."
}
Write-Output "Logs: $logFile"
