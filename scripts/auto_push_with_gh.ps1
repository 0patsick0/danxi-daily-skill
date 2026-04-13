# Auto push script: checks gh, git, commits and creates/pushes remote via gh
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repo
Write-Output "Working dir: $repo"

# Check gh
$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCmd) {
    Write-Error "gh not found in PATH. Please ensure GitHub CLI is installed and available in this shell."
    exit 2
}

Write-Output "gh found: $($ghCmd.Path)"

# Show gh version and auth status
try {
    gh --version
    gh auth status --show-token
} catch {
    Write-Output "gh auth status failed or requires login. Attempting interactive login..."
    gh auth login --web
}

# Ensure we're in a git repo
if (-not (Test-Path .git)) {
    Write-Output "Initializing git repository..."
    git init
    git checkout -b main
    git add .
    git commit -m "feat: initial commit" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Output "Commit failed (possibly nothing to commit)" }
} else {
    Write-Output "Git repo exists. Ensuring branch main and committing changes."
    git checkout -B main
    git add .
    git commit -m "feat: update" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Output "Nothing to commit" }
}

# Determine if origin exists
$origin = $null
try { $origin = git remote get-url origin 2>$null } catch { $origin = $null }
if ([string]::IsNullOrEmpty($origin)) {
    Write-Output "No remote origin configured. Creating repository on GitHub and pushing..."
    # Attempt to create repo under authenticated user/org.
    # Use non-interactive flags where possible; --confirm to skip prompts.
    gh repo create --public --source=. --remote=origin --push --confirm
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        Write-Error "gh repo create failed with exit code $rc"
        exit $rc
    }
} else {
    Write-Output "Remote origin exists: $origin"
    Write-Output "Pushing to origin main..."
    git push -u origin main
}

# Verify remote repo view
Write-Output "Verifying remote via gh..."
try {
    gh repo view --web
} catch {
    try { gh repo view } catch { Write-Output 'gh repo view failed' }
}
Write-Output "DONE"
