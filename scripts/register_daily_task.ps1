param(
    [string]$TaskName = "DanXiDailyReport",
    [string]$Time = "08:00",
    [switch]$EnablePost,
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

if ($Time -notmatch '^(?:[01]\d|2[0-3]):[0-5]\d$') {
    throw "Time must be HH:MM in 24-hour format."
}

$runScript = Join-Path $ProjectRoot "scripts\run_daily.ps1"
$logFile = Join-Path $ProjectRoot "outputs\cron.log"
$envFile = Join-Path $ProjectRoot ".env"

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
