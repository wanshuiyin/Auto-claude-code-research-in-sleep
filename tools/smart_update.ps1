#Requires -Version 5.1
# ARIS Smart Skill Update (PowerShell)
# Intelligently compares local skills with upstream, detects personal
# customizations, and recommends safe update strategy per skill.
#
# Usage:
#   Global (default):
#     .\tools\smart_update.ps1 [-Apply]
#   Project-level (Claude Code):
#     .\tools\smart_update.ps1 -ProjectPath <path> [-Apply]
#   Project-level (Codex CLI):
#     .\tools\smart_update.ps1 -ProjectPath <path> -TargetSubdir '.agents/skills/aris' [-Apply]
#   Custom paths:
#     .\tools\smart_update.ps1 -UpstreamPath <path> -LocalPath <path> [-Apply]
#
#   -Apply: actually perform the updates (default: dry-run analysis only)
#   -ProjectPath: project root — upstream is always the repo's skills/; local targets <ProjectPath>/<TargetSubdir>
#   -TargetSubdir: project-mode skill subdirectory (default: .claude/skills)
#                  common: .claude/skills, .claude/skills/aris, .agents/skills, .agents/skills/aris
#                  must be a relative path
#   -UpstreamPath: explicit upstream skills directory
#   -LocalPath: explicit local skills directory
#
# New-skill policy (-Apply only; dry-run always just reports):
#   default (TTY, no policy switch): each new upstream skill is confirmed one
#                                    by one [y/N]; a decline is remembered in
#                                    <local>\.aris-declined.txt and never re-asked
#   -AddNew:  install every new skill (does NOT un-decline previously declined
#             skills — edit/clear .aris-declined.txt for that)
#   -SkipNew: skip every new skill without recording a decline (same as the
#             automatic behavior when there is no interactive console)
#
# On successful -Apply, writes $env:USERPROFILE\.aris\repo <- this repo's root
# (helper resolution chain layer 4, #366) so copy-installed skills can find tools\.

[CmdletBinding(DefaultParameterSetName = 'Global')]
param(
    [switch]$Apply,
    [switch]$AddNew,
    [switch]$SkipNew,

    [Parameter(ParameterSetName = 'Project', Mandatory = $true)]
    [string]$ProjectPath,

    [Parameter(ParameterSetName = 'Project', Mandatory = $false)]
    [string]$TargetSubdir = '.claude/skills',

    [Parameter(ParameterSetName = 'Explicit', Mandatory = $true)]
    [string]$UpstreamPath,

    [Parameter(ParameterSetName = 'Explicit', Mandatory = $true)]
    [string]$LocalPath
)

$ErrorActionPreference = 'Stop'

if ($AddNew -and $SkipNew) {
    Write-Host "Error: -AddNew and -SkipNew are mutually exclusive" -ForegroundColor Red
    exit 1
}
$NewPolicy = if ($AddNew) { 'add' } elseif ($SkipNew) { 'skip' } else { '' }

# This repo's root (independent of -UpstreamPath overrides) — used for the
# skill-group catalog lookup and the global helper-resolution pointer.
$RepoRoot = Split-Path $PSScriptRoot -Parent

# ─── Resolve upstream & local paths ───────────────────────────────────────────
if ($PSCmdlet.ParameterSetName -eq 'Project') {
    if ([System.IO.Path]::IsPathRooted($TargetSubdir)) {
        Write-Host "Error: -TargetSubdir must be a relative path (got: $TargetSubdir)" -ForegroundColor Red
        Write-Host "Hint: use -LocalPath for absolute paths" -ForegroundColor Yellow
        exit 1
    }

    $ProjectRoot = if ([System.IO.Path]::IsPathRooted($ProjectPath)) {
        $ProjectPath
    } else {
        Join-Path (Get-Location) $ProjectPath
    }
    $ProjectRoot = (Resolve-Path $ProjectRoot -ErrorAction SilentlyContinue).Path
    if (-not $ProjectRoot) {
        Write-Host "Project path not found: $ProjectPath" -ForegroundColor Red
        exit 1
    }
    # Upstream always comes from the repo (same as global)
    $UpstreamDir = Join-Path $RepoRoot 'skills'
    if (-not (Test-Path $UpstreamDir)) {
        $resolved = Join-Path $PSScriptRoot '..\skills' | Resolve-Path -ErrorAction SilentlyContinue
        if ($resolved) { $UpstreamDir = $resolved.Path }
    }
    $TargetSubdirNormalized = $TargetSubdir -replace '/', '\'
    $LocalDir = Join-Path $ProjectRoot $TargetSubdirNormalized
    $Scope = "Project: $ProjectRoot (subdir: $TargetSubdir)"

    # ─── Deprecate nested -TargetSubdir (.claude/skills/aris, .agents/skills/aris) ──
    if ($TargetSubdir -in @('.claude/skills/aris', '.agents/skills/aris')) {
        Write-Host ""
        Write-Host "⚠️  -TargetSubdir $TargetSubdir is DEPRECATED" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Reason: nested 'aris/' subdirectory hides skills from Claude Code's slash-command discovery" -ForegroundColor Yellow
        Write-Host "          (CC only scans .claude/skills/ one level deep)." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Switch to the flat install (use the bash version via WSL, or manual junctions —" -ForegroundColor Yellow
        Write-Host "  see install_aris.ps1 docstring for the manual one-liner)." -ForegroundColor Yellow
        Write-Host ""
        if ($Apply) {
            Write-Host "Refusing to -Apply with deprecated nested target." -ForegroundColor Red
            exit 2
        }
        Write-Host "(continuing dry-run analysis for backward compatibility — no changes will be made)" -ForegroundColor Yellow
    }

    # Platform marker auto-detect: warn on mismatch
    $hasClaudeMarkers = (Test-Path (Join-Path $ProjectRoot 'CLAUDE.md')) -or `
                       (Test-Path (Join-Path $ProjectRoot '.claude\skills')) -or `
                       (Test-Path (Join-Path $ProjectRoot '.claude\settings.json'))
    $hasCodexMarkers  = (Test-Path (Join-Path $ProjectRoot 'AGENTS.md')) -or `
                       (Test-Path (Join-Path $ProjectRoot '.agents\skills')) -or `
                       (Test-Path (Join-Path $ProjectRoot '.codex\config.toml'))
    if ($hasClaudeMarkers -and (-not $hasCodexMarkers) -and $TargetSubdir.StartsWith('.agents')) {
        Write-Host "⚠️  Warning: project has Claude markers but -TargetSubdir points to Codex path ($TargetSubdir)" -ForegroundColor Yellow
    }
    if ($hasCodexMarkers -and (-not $hasClaudeMarkers) -and $TargetSubdir.StartsWith('.claude')) {
        Write-Host "⚠️  Warning: project has Codex markers but -TargetSubdir points to Claude path ($TargetSubdir)" -ForegroundColor Yellow
    }

} elseif ($PSCmdlet.ParameterSetName -eq 'Explicit') {
    $UpstreamDir = $UpstreamPath
    $LocalDir = $LocalPath
    $Scope = "Custom"
} else {
    # Global default
    $UpstreamDir = Join-Path $RepoRoot 'skills'
    if (-not (Test-Path $UpstreamDir)) {
        $resolved = Join-Path $PSScriptRoot '..\skills' | Resolve-Path -ErrorAction SilentlyContinue
        if ($resolved) { $UpstreamDir = $resolved.Path }
    }
    $LocalDir = Join-Path $env:USERPROFILE '.claude\skills'
    $Scope = 'Global'
}

# ─── New-skill confirmation state (declined list + group catalog lookup) ──────
$CatalogPath = Join-Path $RepoRoot 'tools\skill-groups.tsv'
$DeclinedFile = Join-Path $LocalDir '.aris-declined.txt'

function Test-Declined {
    param([string]$Name)
    if (-not (Test-Path $DeclinedFile)) { return $false }
    return (Get-Content -Path $DeclinedFile) -contains $Name
}

function Get-CatalogGroup {
    param([string]$Name)
    if (-not (Test-Path $CatalogPath)) { return '?' }
    foreach ($line in Get-Content -Path $CatalogPath) {
        $f = $line -split "`t"
        if ($f.Length -ge 3 -and $f[0] -eq 'skill' -and $f[1] -eq $Name) { return $f[2] }
    }
    return '?'
}

# Layer-4 helper resolution (#366): a global pointer file lets globally/copy-
# installed skills find $env:USERPROFILE\.aris\repo without a per-project install.
function Ensure-GlobalPointer {
    # $env:USERPROFILE is the Windows PowerShell convention; fall back to $HOME
    # so this also works under pwsh on non-Windows hosts (e.g. CI, WSL testing).
    $userProfile = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
    $pointerDir = Join-Path $userProfile '.aris'
    $pointer = Join-Path $pointerDir 'repo'
    try {
        if (-not (Test-Path $pointerDir)) { New-Item -ItemType Directory -Path $pointerDir -Force | Out-Null }
    } catch { return }
    $cur = $null
    if (Test-Path $pointer) { $cur = (Get-Content -Path $pointer -Raw -ErrorAction SilentlyContinue) }
    if ($cur -and $cur.Trim() -eq $RepoRoot) { return }
    $tmp = "$pointer.tmp.$PID"
    Set-Content -Path $tmp -Value $RepoRoot
    Move-Item -Path $tmp -Destination $pointer -Force
}

# ─── Refuse to operate on symlinked installs ──────────────────────────────────
if (Test-Path $LocalDir) {
    $item = Get-Item $LocalDir -Force -ErrorAction SilentlyContinue
    if ($item -and ($item.LinkType -in @('Junction', 'SymbolicLink'))) {
        Write-Host ""
        Write-Host "✗ Local skill directory is a symlink/junction: $LocalDir" -ForegroundColor Red
        Write-Host "  → $($item.Target)"
        Write-Host ""
        Write-Host "smart_update is for COPIED installs. Symlinked installs are updated by:"
        Write-Host "  cd <aris-repo>; git pull"
        Write-Host ""
        Write-Host "If you need per-project customization, switch to a copied install:"
        Write-Host "  Remove-Item $LocalDir -Force"
        Write-Host "  .\tools\smart_update.ps1 -ProjectPath <project> -TargetSubdir $TargetSubdir -Apply"
        exit 2
    }
}

# install_aris.ps1 creates flat PER-SKILL junctions (the root dir is real), so
# the root-junction check above can't see a managed flat install. The manifest
# is the authoritative marker — refuse project-mode updates when one exists.
if ($ProjectPath) {
    $manifest = Join-Path $ProjectRoot '.aris/installed-skills.txt'
    if (Test-Path $manifest) {
        Write-Host ""
        Write-Host "✗ Managed install detected (manifest: $manifest)" -ForegroundColor Red
        Write-Host ""
        Write-Host "smart_update is for COPIED installs. This project is managed by install_aris.ps1:"
        Write-Host "  cd <aris-repo>; git pull                      # updates content of existing skills"
        Write-Host "  .\tools\install_aris.ps1 $ProjectRoot         # reconciles new/removed skills"
        exit 2
    }
}

# ─── Personal info patterns ───────────────────────────────────────────────────
$PersonalPatterns = @(
    'ssh '
    'SJTUServer'
    'rfyang'
    'yangruofeng'
    'api_key'
    'API_KEY'
    'sk-'
    'token'
    '@sjtu'
    '@gmail'
    '/home/'
    '/Users/'
    'CUDA_VISIBLE'
    'wandb_project'
    'server_ip'
    'gpu_server'
    'screen -'
    'conda activate'
    '192\.168\.'
    '10\.\d+\.'
    '122\.'
)

# Patterns that are actual regex (contain backslash-dot or \d)
function Test-IsRegexPattern {
    param([string]$Pat)
    return ($Pat.Contains('\.') -or $Pat.Contains('\d'))
}

# ─── Header ────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '=== ARIS Smart Skill Update ===' -ForegroundColor Cyan
Write-Host "Scope:    $Scope"
Write-Host "Upstream: $UpstreamDir"
Write-Host "Local:    $LocalDir"
Write-Host ''

if (-not (Test-Path $LocalDir)) {
    Write-Host "Local skills directory not found: $LocalDir" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $UpstreamDir)) {
    Write-Host "Upstream skills directory not found: $UpstreamDir" -ForegroundColor Red
    exit 1
}

# ─── Core comparison function ──────────────────────────────────────────────────
function Compare-SkillDirs {
    param(
        [string]$SrcDir,
        [string]$DstDir,
        [string[]]$Patterns
    )

    $result = @{
        New          = [System.Collections.Generic.List[string]]::new()
        Identical    = [System.Collections.Generic.List[string]]::new()
        Safe         = [System.Collections.Generic.List[string]]::new()
        Merge        = [System.Collections.Generic.List[string]]::new()
        LocalOnly    = [System.Collections.Generic.List[string]]::new()
        UpstreamNames = [System.Collections.Generic.HashSet[string]]::new()
    }

    # Check each upstream skill
    foreach ($skillDir in Get-ChildItem -Path $SrcDir -Directory) {
        $skillName = $skillDir.Name
        if ($skillName -eq 'skills-codex' -or $skillName -eq 'shared-references') { continue }

        [void]$result.UpstreamNames.Add($skillName)

        $upstreamFile = Join-Path $skillDir.FullName 'SKILL.md'
        $localSkillDir = Join-Path $DstDir $skillName
        $localFile = Join-Path $localSkillDir 'SKILL.md'

        if (-not (Test-Path $upstreamFile)) { continue }

        if ((-not (Test-Path $localSkillDir)) -or (-not (Test-Path $localFile))) {
            $result.New.Add($skillName)
            continue
        }

        $upstreamContent = Get-Content -Path $upstreamFile -Raw
        $localContent = Get-Content -Path $localFile -Raw

        if ($upstreamContent -eq $localContent) {
            $result.Identical.Add($skillName)
            continue
        }

        # Different - check for personal info unique to local
        $hasPersonal = $false
        foreach ($pat in $Patterns) {
            $isRegex = Test-IsRegexPattern $pat
            if ($isRegex) {
                $lc = ([regex]::Matches($localContent, $pat)).Count
                $uc = ([regex]::Matches($upstreamContent, $pat)).Count
            } else {
                $lc = ([regex]::Matches($localContent, [regex]::Escape($pat))).Count
                $uc = ([regex]::Matches($upstreamContent, [regex]::Escape($pat))).Count
            }
            if ($lc -gt $uc) {
                $hasPersonal = $true
                break
            }
        }

        if ($hasPersonal) {
            $result.Merge.Add($skillName)
        } else {
            $result.Safe.Add($skillName)
        }
    }

    # Check for local-only skills
    foreach ($skillDir in Get-ChildItem -Path $DstDir -Directory) {
        $skillName = $skillDir.Name
        if ($skillName -eq 'shared-references') { continue }
        if (-not $result.UpstreamNames.Contains($skillName)) {
            $result.LocalOnly.Add($skillName)
        }
    }

    return $result
}

function Show-Section {
    param([string]$Label, $Items, [string]$Color)
    Write-Host "${Label}: $($Items.Count)" -ForegroundColor $Color
    foreach ($s in $Items) { Write-Host "   $s" }
    Write-Host ''
}

function Show-MergeReport {
    param($Items, [string]$Dir, [string[]]$Patterns)
    foreach ($s in $Items) {
        Write-Host "   $s"
        $f = Join-Path $Dir "$s\SKILL.md"
        if (Test-Path $f) {
            $content = Get-Content -Path $f -Raw
            foreach ($pat in $Patterns) {
                $isRegex = Test-IsRegexPattern $pat
                if ($isRegex) {
                    $escaped = $pat
                } else {
                    $escaped = [regex]::Escape($pat)
                }
                $m = [regex]::Match($content, ".*$escaped.*")
                if ($m.Success) {
                    Write-Host "     -> contains: $($m.Value.Trim())" -ForegroundColor Yellow
                    break
                }
            }
        }
    }
}

# New-skill three-state policy: interactive confirm / -AddNew / -SkipNew.
# A skill already in .aris-declined.txt is never re-asked and never installed —
# not even by -AddNew (only editing/clearing the declined file restores it).
function Resolve-NewSkillPolicy {
    param([string[]]$NewList, [string]$Policy)
    $toInstall = [System.Collections.Generic.List[string]]::new()
    $skipped = [System.Collections.Generic.List[string]]::new()
    $justDeclined = [System.Collections.Generic.List[string]]::new()
    $interactive = -not [Console]::IsInputRedirected

    foreach ($name in $NewList) {
        if (Test-Declined $name) { continue }
        switch ($Policy) {
            'add' { $toInstall.Add($name) }
            'skip' { $skipped.Add($name) }
            default {
                if ($interactive) {
                    $grp = Get-CatalogGroup $name
                    $reply = Read-Host "  install new skill $($name.PadRight(30)) (group: $grp) [y/N]"
                    if ($reply -match '^[yY]') { $toInstall.Add($name) } else { $justDeclined.Add($name) }
                } else {
                    $skipped.Add($name)
                }
            }
        }
    }

    if ($justDeclined.Count -gt 0) {
        $existing = @()
        if (Test-Path $DeclinedFile) { $existing = @(Get-Content -Path $DeclinedFile) }
        $merged = @($existing + $justDeclined) | Where-Object { $_ } | Sort-Object -Unique
        $tmp = "$DeclinedFile.tmp.$PID"
        Set-Content -Path $tmp -Value $merged
        Move-Item -Path $tmp -Destination $DeclinedFile -Force
    }

    return @{ ToInstall = $toInstall; Skipped = $skipped; JustDeclined = $justDeclined }
}

function Invoke-SafeUpdate {
    param(
        $NewList,
        $SafeList,
        [string]$SrcDir,
        [string]$DstDir,
        [string]$SharedDir
    )
    foreach ($s in $NewList) {
        $src = Join-Path $SrcDir $s
        $dst = Join-Path $DstDir $s
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        Write-Host "  + Added: $s" -ForegroundColor Green
    }

    foreach ($s in $SafeList) {
        $src = Join-Path $SrcDir $s
        $dst = Join-Path $DstDir $s
        if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
        Copy-Item -Path $src -Destination $dst -Recurse -Force
        Write-Host "  ^ Updated: $s" -ForegroundColor Cyan
    }

    if ($SharedDir -and (Test-Path $SharedDir)) {
        Copy-Item -Path $SharedDir -Destination (Join-Path $DstDir 'shared-references') -Recurse -Force
        Write-Host '  ^ Updated: shared-references' -ForegroundColor Cyan
    }
}

# ─── Run comparison ─────────────────────────────────────────────────────────────
$r = Compare-SkillDirs -SrcDir $UpstreamDir -DstDir $LocalDir -Patterns $PersonalPatterns

# ─── Report ────────────────────────────────────────────────────────────────────
Show-Section 'Identical (no action needed)' $r.Identical 'Green'

# Pre-declined subset of $r.New (informational only — the decision of what to
# install/skip/prompt is only made inside the -Apply block below).
$NewPredeclined = @($r.New | Where-Object { Test-Declined $_ })
Write-Host "New skills upstream (confirmed one-by-one on -Apply, unless -AddNew/-SkipNew): $($r.New.Count)" -ForegroundColor Green
foreach ($s in $r.New) {
    if (Test-Declined $s) {
        Write-Host "   $s (previously declined — stays skipped unless -AddNew)" -ForegroundColor Yellow
    } else {
        Write-Host "   $s"
    }
}
Write-Host ''

Show-Section 'Updated upstream, no personal info (safe to replace)' $r.Safe 'Cyan'

Write-Host "Updated upstream + local customizations (needs manual merge): $($r.Merge.Count)" -ForegroundColor Yellow
Show-MergeReport $r.Merge $LocalDir $PersonalPatterns
Write-Host ''

Write-Host "Local-only skills (yours, not in upstream): $($r.LocalOnly.Count)"
foreach ($s in $r.LocalOnly) { Write-Host "   $s" }
Write-Host ''

# ─── Summary ───────────────────────────────────────────────────────────────────
$Total = $r.New.Count + $r.Identical.Count + $r.Safe.Count + $r.Merge.Count
Write-Host '=== Summary ===' -ForegroundColor Cyan
Write-Host "Total upstream skills: $Total"
Write-Host "  Up to date:  $($r.Identical.Count)" -ForegroundColor Green
Write-Host "  New upstream: $($r.New.Count)" -ForegroundColor Green -NoNewline
Write-Host " (requires confirmation on -Apply; $($NewPredeclined.Count) previously declined)"
Write-Host "  Safe update: $($r.Safe.Count)" -ForegroundColor Cyan
Write-Host "  Need merge:  $($r.Merge.Count)" -ForegroundColor Yellow
Write-Host "  Local only:  $($r.LocalOnly.Count)"
Write-Host ''

if ($Apply) {
    Write-Host 'Applying safe updates...' -ForegroundColor Cyan

    $newDecision = Resolve-NewSkillPolicy -NewList $r.New -Policy $NewPolicy
    $sharedUpstream = Join-Path $UpstreamDir 'shared-references'
    Invoke-SafeUpdate -NewList $newDecision.ToInstall -SafeList $r.Safe -SrcDir $UpstreamDir -DstDir $LocalDir -SharedDir $sharedUpstream

    Write-Host ''
    Write-Host "Done! $($newDecision.ToInstall.Count) new + $($r.Safe.Count) updated." -ForegroundColor Green

    if ($newDecision.Skipped.Count -gt 0) {
        Write-Host "$($newDecision.Skipped.Count) new skill(s) skipped, not declined: $($newDecision.Skipped -join ', ')" -ForegroundColor Yellow
        Write-Host "   Re-run with -AddNew to install them (or re-run interactively)." -ForegroundColor Yellow
    }
    if ($newDecision.JustDeclined.Count -gt 0) {
        Write-Host "Declined just now (recorded in $DeclinedFile, won't be asked again): $($newDecision.JustDeclined -join ', ')"
    }
    if ($NewPredeclined.Count -gt 0) {
        Write-Host "Previously declined, still skipped: $($NewPredeclined.Count) (edit $DeclinedFile to reconsider)"
    }

    if ($r.Merge.Count -gt 0) {
        Write-Host "$($r.Merge.Count) skills have personal customizations and were NOT updated." -ForegroundColor Yellow
        Write-Host "   Review manually: $($r.Merge -join ', ')" -ForegroundColor Yellow
        Write-Host "   Tip: diff the local and upstream SKILL.md files to merge changes" -ForegroundColor Yellow
    }

    Ensure-GlobalPointer
} else {
    switch ($PSCmdlet.ParameterSetName) {
        'Project'  { $cmdHint = ".\tools\smart_update.ps1 -ProjectPath `"$ProjectRoot`" -Apply" }
        'Explicit' { $cmdHint = ".\tools\smart_update.ps1 -UpstreamPath `"$UpstreamDir`" -LocalPath `"$LocalDir`" -Apply" }
        default    { $cmdHint = '.\tools\smart_update.ps1 -Apply' }
    }
    Write-Host 'Dry run complete. Run with -Apply to perform updates:' -ForegroundColor Yellow
    Write-Host "  $cmdHint" -ForegroundColor Green
}
Write-Host ''
