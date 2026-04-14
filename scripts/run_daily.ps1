param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py scripts/generate_daily.py @Args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python scripts/generate_daily.py @Args
} else {
    Write-Error "Python runtime not found. Please install Python or ensure 'py'/'python' is in PATH."
    exit 127
}
