#Requires -Version 5.1
<#
.SYNOPSIS
    Project-local ARIS skill installation for Windows.

.DESCRIPTION
    Creates one flat junction per ARIS skill so Claude Code and Codex can
    discover slash commands at one directory level:

      Claude: <project>\.claude\skills\<skill-name>
      Codex:  <project>\.agents\skills\<skill-name>

    Managed entries are tracked in .aris manifests. The script never replaces
    real files or user-owned skill directories; conflicts must be resolved
    explicitly.

    Selective install (catalog: tools\skill-groups.tsv in the ARIS repo):
      -Groups A,B     install only these skill groups (see -ListGroups)
      -Skills X,Y     additionally install these skills (clears declined mark)
      -Exclude X,Y    never install these skills (recorded as declined)
      -All            install every upstream skill (legacy default)
      -AddNew         reconcile: accept all upstream skills not yet installed
      -SkipNew        reconcile: skip new upstream skills without prompting
      -ListGroups     print the group catalog and exit
      -Quiet          no prompts; non-interactive fallback for every decision
      With no selection flags: a fresh install on a real console walks an
      interactive per-group Y/n/e menu; a fresh install under -Quiet or a
      redirected console installs everything (legacy behavior).
      Reconcile keeps exactly what the manifest says is installed; NEW
      upstream skills need per-skill confirmation (declined ones are
      remembered in .aris\skills-declined.txt and never re-asked).

.PARAMETER Groups
    Comma-separated catalog group ids to install on a fresh install (or
    re-enable on reconcile).

.PARAMETER Skills
    Comma-separated skill names to install on a fresh install, or re-enable
    (un-decline) on reconcile.

.PARAMETER Exclude
    Comma-separated skill names to never install; removed and recorded as
    declined on reconcile.

.PARAMETER All
    Install every upstream skill. Cannot be combined with -Groups/-Skills
    (only with -Exclude).

.PARAMETER AddNew
    On reconcile, silently accept every new upstream skill not yet installed
    or declined.

.PARAMETER SkipNew
    On reconcile, leave new upstream skills uninstalled without prompting or
    recording them as declined (they are asked about again next time).

.PARAMETER ListGroups
    Print the skill-group catalog (from tools\skill-groups.tsv) and exit.

.PARAMETER Quiet
    Suppress interactive prompts; every decision that would otherwise prompt
    falls back to its non-interactive default (see catalog notes above).
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$ProjectPath = (Get-Location).Path,

    [ValidateSet('auto', 'claude', 'codex')]
    [string]$Platform = 'auto',

    [string]$ArisRepo = '',

    [switch]$DryRun,
    [switch]$NoDoc,
    [switch]$Reconcile,
    [switch]$Uninstall,
    [string[]]$ReplaceLink = @(),
    [switch]$FromOld,
    [ValidateSet('', 'keep-user', 'prefer-upstream')]
    [string]$MigrateCopy = '',
    [switch]$ClearStaleLock,

    # Selective install (#366 parity with install_aris.sh).
    [string]$Groups = '',
    [string]$Skills = '',
    [string]$Exclude = '',
    [switch]$All,
    [switch]$AddNew,
    [switch]$SkipNew,
    [switch]$ListGroups,
    [switch]$Quiet,

    # Kept only to preserve CLI recognition. It is intentionally unsafe for
    # this installer and is rejected in favor of per-skill -ReplaceLink.
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$ManifestVersion = '1'
$SafeNameRegex = '^[A-Za-z0-9][A-Za-z0-9._-]*$'
$SupportNames = @('shared-references')
$CatalogRel = 'tools/skill-groups.tsv'
$GlobalPointerDir = Join-Path $HOME '.aris'
$GlobalPointerPath = Join-Path $GlobalPointerDir 'repo'
$script:LockDir = $null
$script:LockAcquired = $false

function Die {
    param([string]$Message)
    throw $Message
}

function Normalize-PathString {
    param([string]$Path)
    return ([System.IO.Path]::GetFullPath($Path)).TrimEnd([char[]]@('\', '/'))
}

function Same-Path {
    param([string]$Left, [string]$Right)
    return [System.StringComparer]::OrdinalIgnoreCase.Equals((Normalize-PathString $Left), (Normalize-PathString $Right))
}

function Test-PathInside {
    param([string]$Path, [string]$Root)
    $normalizedPath = Normalize-PathString $Path
    $normalizedRoot = Normalize-PathString $Root
    if ([System.StringComparer]::OrdinalIgnoreCase.Equals($normalizedPath, $normalizedRoot)) {
        return $true
    }
    $prefix = $normalizedRoot + [System.IO.Path]::DirectorySeparatorChar
    return $normalizedPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Join-PathSegments {
    param([string]$Root, [string[]]$Segments)
    $path = $Root
    foreach ($segment in $Segments) {
        if ([string]::IsNullOrEmpty($path)) {
            $path = $segment
        } else {
            $path = Join-Path $path $segment
        }
    }
    return $path
}

function Get-PathSegments {
    param([string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetPathRoot($full)
    if (-not $root) {
        $root = ''
    }
    $rest = $full.Substring($root.Length).TrimEnd([char[]]@('\', '/'))
    [string[]]$segments = @()
    if ($rest) {
        $segments = @($rest -split '[\\/]' | Where-Object { $_ -ne '' })
    }
    return [pscustomobject]@{
        Root = $root
        Segments = $segments
    }
}

function Resolve-ReparseChain {
    param([string]$Path)
    $current = [System.IO.Path]::GetFullPath($Path)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    for ($depth = 0; $depth -lt 40; $depth++) {
        $normalizedCurrent = Normalize-PathString $current
        if (-not $seen.Add($normalizedCurrent)) {
            Die "reparse point cycle detected while resolving: $Path"
        }
        $parts = Get-PathSegments $current
        $candidate = $parts.Root
        $rewrote = $false
        for ($index = 0; $index -lt $parts.Segments.Count; $index++) {
            if ([string]::IsNullOrEmpty($candidate)) {
                $candidate = $parts.Segments[$index]
            } else {
                $candidate = Join-Path $candidate $parts.Segments[$index]
            }
            $item = Get-PathItem $candidate
            if ($null -eq $item) {
                return $normalizedCurrent
            }
            if (-not (Test-LinkItem $item)) {
                continue
            }
            $target = Get-LinkTarget $candidate
            if (-not $target) {
                return $normalizedCurrent
            }
            [string[]]$remaining = @()
            if (($index + 1) -lt $parts.Segments.Count) {
                $remaining = @($parts.Segments[($index + 1)..($parts.Segments.Count - 1)])
            }
            $current = Join-PathSegments $target $remaining
            $rewrote = $true
            break
        }
        if (-not $rewrote) {
            return $normalizedCurrent
        }
    }
    Die "reparse point chain too deep while resolving: $Path"
}

function Test-ResolvedPathInside {
    param([string]$Path, [string]$Root)
    return Test-PathInside (Resolve-ReparseChain $Path) (Resolve-ReparseChain $Root)
}

function Read-Text {
    param([string]$Path)
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Write-Text {
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Get-PathItem {
    param([string]$Path)
    try {
        return Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    } catch {
        return $null
    }
}

function Test-LinkItem {
    param($Item)
    return $null -ne $Item -and $Item.LinkType -in @('Junction', 'SymbolicLink')
}

function Get-LinkTarget {
    param([string]$Path)
    $item = Get-PathItem $Path
    if (-not (Test-LinkItem $item)) {
        return ''
    }
    $target = $item.Target
    if ($target -is [array]) {
        $target = $target[0]
    }
    if (-not [System.IO.Path]::IsPathRooted([string]$target)) {
        $target = Join-Path (Split-Path -Parent $Path) ([string]$target)
    }
    return Normalize-PathString ([string]$target)
}

function Join-RelativePath {
    param([string]$Root, [string]$Relative)
    return Join-Path $Root ($Relative.Replace([char]'/', [char][System.IO.Path]::DirectorySeparatorChar))
}

function Resolve-ArisRepo {
    if ($ArisRepo) {
        if (-not (Test-Path -LiteralPath (Join-Path $ArisRepo 'skills') -PathType Container)) {
            Die "-ArisRepo path has no skills directory: $ArisRepo"
        }
        return (Resolve-Path -LiteralPath $ArisRepo).ProviderPath
    }

    $parent = Split-Path -Parent $PSScriptRoot
    if (Test-Path -LiteralPath (Join-Path $parent 'skills') -PathType Container) {
        return (Resolve-Path -LiteralPath $parent).ProviderPath
    }
    if ($env:ARIS_REPO -and (Test-Path -LiteralPath (Join-Path $env:ARIS_REPO 'skills') -PathType Container)) {
        return (Resolve-Path -LiteralPath $env:ARIS_REPO).ProviderPath
    }
    foreach ($candidate in @(
        (Join-Path $env:USERPROFILE 'Auto-claude-code-research-in-sleep'),
        (Join-Path $env:USERPROFILE 'aris_repo'),
        (Join-Path $env:USERPROFILE 'Desktop\Auto-claude-code-research-in-sleep'),
        (Join-Path $env:USERPROFILE '.codex\Auto-claude-code-research-in-sleep'),
        (Join-Path $env:USERPROFILE '.claude\Auto-claude-code-research-in-sleep')
    )) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'skills') -PathType Container) {
            return (Resolve-Path -LiteralPath $candidate).ProviderPath
        }
    }
    Die 'cannot find ARIS repo. Use -ArisRepo PATH or set ARIS_REPO.'
}

function Detect-Platform {
    param([string]$ProjectRoot)
    $hasClaude = (Test-Path -LiteralPath (Join-Path $ProjectRoot 'CLAUDE.md')) -or
        (Test-Path -LiteralPath (Join-Path $ProjectRoot '.claude\skills')) -or
        (Test-Path -LiteralPath (Join-Path $ProjectRoot '.claude\settings.json'))
    $hasCodex = (Test-Path -LiteralPath (Join-Path $ProjectRoot 'AGENTS.md')) -or
        (Test-Path -LiteralPath (Join-Path $ProjectRoot '.agents\skills')) -or
        (Test-Path -LiteralPath (Join-Path $ProjectRoot '.codex\config.toml'))
    if ($hasClaude -and $hasCodex) {
        Die 'project has both Claude and Codex markers; pass -Platform claude or -Platform codex'
    }
    if ($hasClaude) { return 'claude' }
    if ($hasCodex) { return 'codex' }
    Die 'cannot auto-detect platform; pass -Platform claude or -Platform codex'
}

function New-Config {
    param([string]$ProjectRoot, [string]$RepoRoot, [string]$SelectedPlatform)
    if ($SelectedPlatform -eq 'claude') {
        return [pscustomobject]@{
            Platform = 'claude'
            RepoRoot = $RepoRoot
            SourceRoot = Join-Path $RepoRoot 'skills'
            SourceRelPrefix = 'skills'
            TargetRel = '.claude\skills'
            TargetRelDisplay = '.claude/skills'
            LegacyNestedRel = '.claude\skills\aris'
            ManifestName = 'installed-skills.txt'
            ManifestPrevName = 'installed-skills.txt.prev'
            DeclinedName = 'skills-declined.txt'
            LockName = '.install.lock.d'
            DocName = 'CLAUDE.md'
            BlockBegin = '<!-- ARIS:BEGIN -->'
            BlockEnd = '<!-- ARIS:END -->'
            Title = 'ARIS Skill Scope'
        }
    }
    return [pscustomobject]@{
        Platform = 'codex'
        RepoRoot = $RepoRoot
        SourceRoot = Join-Path $RepoRoot 'skills\skills-codex'
        SourceRelPrefix = 'skills/skills-codex'
        TargetRel = '.agents\skills'
        TargetRelDisplay = '.agents/skills'
        LegacyNestedRel = '.agents\skills\aris'
        ManifestName = 'installed-skills-codex.txt'
        ManifestPrevName = 'installed-skills-codex.txt.prev'
        DeclinedName = 'skills-declined-codex.txt'
        LockName = '.install-codex.lock.d'
        DocName = 'AGENTS.md'
        BlockBegin = '<!-- ARIS-CODEX:BEGIN -->'
        BlockEnd = '<!-- ARIS-CODEX:END -->'
        Title = 'ARIS Codex Skill Scope'
    }
}

function Test-SafeName {
    param([string]$Name)
    return $Name -match $SafeNameRegex
}

# ─── Selective install (#366 parity) ───────────────────────────────────────
# Catalog = tools/skill-groups.tsv in the ARIS repo, shared across platforms.
# Two record types (tab-separated):
#   group\t<id>\t<display>\t<description>
#   skill\t<name>\t<group-id>\t<requires: comma list or "->
# Selection state lives in two project files:
#   .aris/installed-skills[-codex].txt  — what IS installed (manifest)
#   .aris/skills-declined[-codex].txt   — skills the user explicitly said no
#                                         to; never re-prompted on reconcile.
# "Skipped" (via -SkipNew / -Quiet) is NOT declined — those skills are asked
# about again on the next interactive reconcile.

function Get-CommaList {
    # Comma-prefixed returns: PowerShell unrolls IEnumerable return values onto
    # the pipeline, so a 0- or 1-element array collapses to $null or a bare
    # scalar at the call site unless wrapped as the sole pipeline object.
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return ,@() }
    return ,@($Value -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Test-IsInteractive {
    if ($Quiet) { return $false }
    try { return -not [Console]::IsInputRedirected } catch { return $false }
}

function Load-Catalog {
    param([string]$Path)
    $catalog = [pscustomobject]@{
        Path = $Path
        Exists = (Test-Path -LiteralPath $Path -PathType Leaf)
        Groups = New-Object System.Collections.Generic.List[object]
        SkillGroup = @{}
        SkillRequires = @{}
        GroupSkills = @{}
    }
    if (-not $catalog.Exists) { return $catalog }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $fields = $line -split "`t"
        if ($fields.Count -lt 4) { continue }
        if ($fields[0] -eq 'group') {
            $gid = $fields[1]
            $catalog.Groups.Add([pscustomobject]@{ Id = $gid; Display = $fields[2]; Desc = $fields[3] })
            if (-not $catalog.GroupSkills.ContainsKey($gid)) {
                $catalog.GroupSkills[$gid] = New-Object System.Collections.Generic.List[string]
            }
        } elseif ($fields[0] -eq 'skill') {
            $name = $fields[1]
            $gid = $fields[2]
            $catalog.SkillGroup[$name] = $gid
            if (-not $catalog.GroupSkills.ContainsKey($gid)) {
                $catalog.GroupSkills[$gid] = New-Object System.Collections.Generic.List[string]
            }
            $catalog.GroupSkills[$gid].Add($name)
            $requires = $fields[3]
            if ($requires -and $requires -ne '-') {
                $catalog.SkillRequires[$name] = Get-CommaList $requires
            } else {
                $catalog.SkillRequires[$name] = @()
            }
        }
    }
    return $catalog
}

function Get-CatalogGroupIds { param($Catalog) return ,@($Catalog.Groups | ForEach-Object { $_.Id }) }

function Get-CatalogSkillsInGroup {
    param($Catalog, [string]$GroupId)
    if ($Catalog.GroupSkills.ContainsKey($GroupId)) { return ,@($Catalog.GroupSkills[$GroupId]) }
    return ,@()
}

function Get-CatalogGroupOf {
    param($Catalog, [string]$Name)
    if ($Catalog.SkillGroup.ContainsKey($Name)) { return $Catalog.SkillGroup[$Name] }
    return $null
}

function Get-CatalogRequires {
    param($Catalog, [string]$Name)
    if ($Catalog.SkillRequires.ContainsKey($Name)) { return ,@($Catalog.SkillRequires[$Name]) }
    return ,@()
}

function Show-GroupCatalog {
    param($Catalog)
    if (-not $Catalog.Exists) { Die "skill catalog not found: $($Catalog.Path)" }
    Write-Host "Skill groups (from $($Catalog.Path)):"
    foreach ($g in $Catalog.Groups) {
        $groupSkills = Get-CatalogSkillsInGroup $Catalog $g.Id
        Write-Host ''
        Write-Host ("  {0,-14} {1} - {2}  [{3} skills]" -f $g.Id, $g.Display, $g.Desc, $groupSkills.Count)
        foreach ($name in $groupSkills) { Write-Host "      $name" }
    }
}

function Read-DeclinedSet {
    param([string]$Path)
    $set = New-Object System.Collections.Generic.HashSet[string]
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
            $trimmed = $line.Trim()
            if ($trimmed) { $set.Add($trimmed) | Out-Null }
        }
    }
    return ,$set
}

# Final declined set = (old declined ∪ new declines ∪ excludes ∪ fresh
# unselected) minus everything selected. Atomic write, same dir as target.
function Save-DeclinedSet {
    param(
        [string]$Path,
        [System.Collections.Generic.HashSet[string]]$Declined,
        [System.Collections.Generic.HashSet[string]]$Selected
    )
    if ($DryRun) { return }
    $final = @($Declined | Where-Object { -not $Selected.Contains($_) } | Sort-Object)
    $existed = Test-Path -LiteralPath $Path -PathType Leaf
    if ($final.Count -eq 0 -and -not $existed) { return }
    $dir = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $content = if ($final.Count -gt 0) { ($final -join "`n") + "`n" } else { '' }
    $tmp = "$Path.tmp.$PID"
    Write-Text $tmp $content
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

# Auto-include hard pipeline deps (catalog `requires` column, transitively).
# A dep excluded this run is never auto-added — warn instead.
function Expand-SelectionDeps {
    param(
        $Catalog,
        [System.Collections.Generic.HashSet[string]]$Selected,
        [System.Collections.Generic.HashSet[string]]$ExcludeSet,
        [System.Collections.Generic.HashSet[string]]$UpstreamSkillNames
    )
    if (-not $Catalog.Exists) { return }
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($name in @($Selected)) {
            foreach ($dep in (Get-CatalogRequires $Catalog $name)) {
                if ($Selected.Contains($dep)) { continue }
                if ($ExcludeSet.Contains($dep)) {
                    Write-Warning "'$name' requires '$dep' but it is excluded -- that pipeline phase will break"
                    continue
                }
                if (-not $UpstreamSkillNames.Contains($dep)) { continue }
                $Selected.Add($dep) | Out-Null
                Write-Host "  -> auto-including '$dep' (required by '$name')"
                $changed = $true
            }
        }
    }
}

# Validate -Groups/-Skills names against catalog + upstream.
function Test-SelectionFlags {
    param($Catalog, [string[]]$GroupsList, [string[]]$SkillsList, [System.Collections.Generic.HashSet[string]]$UpstreamSkillNames)
    if ($GroupsList.Count -gt 0) {
        if (-not $Catalog.Exists) { Die "-Groups needs the catalog at $($Catalog.Path) (update your aris-repo clone)" }
        # Get-CatalogGroupIds is already comma-protected (see note above); do
        # not re-wrap with @() here or the result nests into a 1-element array.
        $validIds = Get-CatalogGroupIds $Catalog
        foreach ($g in $GroupsList) {
            if ($validIds -notcontains $g) { Die "unknown group '$g' -- run with -ListGroups to see valid ids" }
        }
    }
    foreach ($s in $SkillsList) {
        if (-not $UpstreamSkillNames.Contains($s)) { Die "unknown skill '$s' (not an upstream skill)" }
    }
}

# Interactive group menu (fresh install on a real console, no selection flags).
function Read-InteractiveSelection {
    param($Catalog, [System.Collections.Generic.HashSet[string]]$UpstreamSkillNames, [System.Collections.Generic.HashSet[string]]$Selected)
    Write-Host ''
    Write-Host "Interactive skill selection -- per group: Y=install all, n=skip, e=pick per skill."
    foreach ($g in $Catalog.Groups) {
        # Capture the (comma-protected) catalog result into a real variable
        # first, then filter — piping the function call straight into
        # Where-Object would hand it the whole array as a single item.
        $groupSkillsInCatalog = Get-CatalogSkillsInGroup $Catalog $g.Id
        $groupSkills = @($groupSkillsInCatalog | Where-Object { $UpstreamSkillNames.Contains($_) })
        if ($groupSkills.Count -eq 0) { continue }
        Write-Host ''
        Write-Host "$($g.Display) ($($g.Id)) -- $($g.Desc)"
        foreach ($name in $groupSkills) { Write-Host "    $name" }
        $reply = Read-Host "Install group '$($g.Id)' ($($groupSkills.Count) skills)? [Y/n/e]"
        if ($reply -match '^[nN]') {
            continue
        } elseif ($reply -match '^[eE]') {
            foreach ($name in $groupSkills) {
                $r2 = Read-Host "  install $name [Y/n]"
                if ($r2 -notmatch '^[nN]') { $Selected.Add($name) | Out-Null }
            }
        } else {
            foreach ($name in $groupSkills) { $Selected.Add($name) | Out-Null }
        }
    }
    # Upstream skills the catalog doesn't know yet (catalog drift): never drop silently.
    $ungrouped = @($UpstreamSkillNames | Where-Object { -not (Get-CatalogGroupOf $Catalog $_) } | Sort-Object)
    if ($ungrouped.Count -gt 0) {
        Write-Host ''
        Write-Host 'Skills not in the catalog yet:'
        foreach ($name in $ungrouped) { Write-Host "    $name" }
        foreach ($name in $ungrouped) {
            $r2 = Read-Host "  install $name [Y/n]"
            if ($r2 -notmatch '^[nN]') { $Selected.Add($name) | Out-Null }
        }
    }
}

# Build the selected-skill set for this run.
function Build-Selection {
    param($Catalog, $Manifest, [System.Collections.Generic.HashSet[string]]$UpstreamSkillNames, [string]$DeclinedPath, [bool]$IsFresh)

    $declinedCandidates = Read-DeclinedSet $DeclinedPath
    $excludeList = Get-CommaList $Exclude
    $excludeSet = New-Object System.Collections.Generic.HashSet[string]
    foreach ($e in $excludeList) {
        $excludeSet.Add($e) | Out-Null
        $declinedCandidates.Add($e) | Out-Null
    }

    $groupsList = Get-CommaList $Groups
    $skillsList = Get-CommaList $Skills
    Test-SelectionFlags $Catalog $groupsList $skillsList $UpstreamSkillNames

    $selected = New-Object System.Collections.Generic.HashSet[string]
    $hasSelectionFlags = ($groupsList.Count -gt 0 -or $skillsList.Count -gt 0)

    if ($IsFresh) {
        $subsetChoice = $false
        if ($All -or (-not $hasSelectionFlags -and -not (Test-IsInteractive))) {
            foreach ($n in $UpstreamSkillNames) { $selected.Add($n) | Out-Null }
        } elseif ($hasSelectionFlags) {
            $subsetChoice = $true
            foreach ($g in $groupsList) {
                foreach ($n in (Get-CatalogSkillsInGroup $Catalog $g)) {
                    if ($UpstreamSkillNames.Contains($n)) { $selected.Add($n) | Out-Null }
                }
            }
            foreach ($n in $skillsList) { $selected.Add($n) | Out-Null }
        } elseif ($Catalog.Exists) {
            $subsetChoice = $true
            Read-InteractiveSelection $Catalog $UpstreamSkillNames $selected
        } else {
            Write-Warning "catalog missing at $($Catalog.Path) -- falling back to full install"
            foreach ($n in $UpstreamSkillNames) { $selected.Add($n) | Out-Null }
        }
        # Explicit subset choice ⇒ remember the rest as declined (won't re-ask).
        if ($subsetChoice) {
            foreach ($n in $UpstreamSkillNames) {
                if (-not $selected.Contains($n)) { $declinedCandidates.Add($n) | Out-Null }
            }
        }
    } else {
        # Reconcile: installed set = manifest ∩ upstream (auto-detected).
        foreach ($entry in $Manifest.Entries) {
            if ($entry.Kind -eq 'skill' -and $UpstreamSkillNames.Contains($entry.Name)) {
                $selected.Add($entry.Name) | Out-Null
            }
        }
        # Flag-based additions re-enable previously declined skills.
        foreach ($g in $groupsList) {
            foreach ($n in (Get-CatalogSkillsInGroup $Catalog $g)) {
                if ($UpstreamSkillNames.Contains($n)) { $selected.Add($n) | Out-Null }
            }
        }
        foreach ($n in $skillsList) { $selected.Add($n) | Out-Null }

        # NEW upstream skills: not installed, not declined, not just selected.
        $newSkills = @($UpstreamSkillNames | Where-Object { -not $selected.Contains($_) -and -not $declinedCandidates.Contains($_) } | Sort-Object)
        if ($newSkills.Count -gt 0) {
            if ($All -or $AddNew) {
                foreach ($n in $newSkills) { $selected.Add($n) | Out-Null }
                Write-Host "-> adding $($newSkills.Count) new upstream skill(s) (-All/-AddNew)"
            } elseif ($SkipNew -or -not (Test-IsInteractive)) {
                # warn (not Write-Host): must stay visible under -Quiet — silently
                # missing new skills is exactly the failure mode this feature fixes.
                Write-Warning "new upstream skills NOT installed: $($newSkills -join ',')"
                Write-Warning '  (rerun interactively to be asked, or pass -AddNew / -Skills NAME)'
            } else {
                Write-Host ''
                Write-Host 'New skills appeared upstream since your last install:'
                foreach ($name in $newSkills) {
                    $grp = Get-CatalogGroupOf $Catalog $name
                    if (-not $grp) { $grp = '?' }
                    $reply = Read-Host "  install new skill $name (group: $grp) [y/N]"
                    if ($reply -match '^[yY]') { $selected.Add($name) | Out-Null }
                    else { $declinedCandidates.Add($name) | Out-Null }
                }
            }
        }
    }

    # Excludes beat every other source (manifest, groups, deps, new skills):
    # prune before dep expansion so an excluded pipeline doesn't drag deps in,
    # and Expand-SelectionDeps itself refuses to re-add excluded names.
    foreach ($e in $excludeSet) { $selected.Remove($e) | Out-Null }
    Expand-SelectionDeps $Catalog $selected $excludeSet $UpstreamSkillNames

    if ($selected.Count -eq 0) {
        Die 'selection is empty -- nothing to install (use -All or -Groups/-Skills)'
    }

    return [pscustomobject]@{ Selected = $selected; DeclinedCandidates = $declinedCandidates }
}

# Layer-4 helper resolution: a global pointer file lets globally/copy-installed
# skills find $ArisRepo\tools without a per-project install.
function Ensure-GlobalPointer {
    param([string]$RepoRoot)
    if ($DryRun) { return }
    try {
        New-Item -ItemType Directory -Force -Path $GlobalPointerDir -ErrorAction Stop | Out-Null
    } catch {
        Write-Warning "cannot create $GlobalPointerDir -- skipping global pointer"
        return
    }
    $current = ''
    if (Test-Path -LiteralPath $GlobalPointerPath -PathType Leaf) {
        $current = (Read-Text $GlobalPointerPath).Trim()
    }
    if ($current -eq $RepoRoot) { return }
    $tmp = "$GlobalPointerPath.tmp.$PID"
    Write-Text $tmp ($RepoRoot + "`n")
    Move-Item -LiteralPath $tmp -Destination $GlobalPointerPath -Force
    Write-Host "  + global pointer $GlobalPointerPath -> $RepoRoot"
}

function Build-Inventory {
    param($Config)
    if (-not (Test-Path -LiteralPath $Config.SourceRoot -PathType Container)) {
        Die "source skills directory does not exist: $($Config.SourceRoot)"
    }

    $entries = New-Object System.Collections.Generic.List[object]
    $resolvedRepoRoot = Resolve-ReparseChain $Config.RepoRoot
    foreach ($dir in Get-ChildItem -LiteralPath $Config.SourceRoot -Directory | Sort-Object Name) {
        $name = $dir.Name
        if (-not (Test-SafeName $name)) {
            Write-Warning "skipping unsafe upstream name: $name"
            continue
        }
        $resolved = Resolve-ReparseChain $dir.FullName
        if (-not (Test-PathInside $resolved $resolvedRepoRoot)) {
            Write-Warning "skipping upstream link leading outside ARIS repo: $name -> $resolved"
            continue
        }
        $kind = $null
        if ($SupportNames -contains $name) {
            $kind = 'support'
        } elseif (Test-Path -LiteralPath (Join-Path $dir.FullName 'SKILL.md') -PathType Leaf) {
            $kind = 'skill'
        } else {
            continue
        }
        $sourceRel = "$($Config.SourceRelPrefix)/$name"
        $targetRel = ($Config.TargetRelDisplay + '/' + $name)
        $entries.Add([pscustomobject]@{
            Kind = $kind
            Name = $name
            SourceRel = $sourceRel
            TargetRel = $targetRel
            ExpectedTarget = (Normalize-PathString $dir.FullName)
        })
    }
    if ($entries.Count -eq 0) {
        Die "upstream inventory is empty: $($Config.SourceRoot)"
    }
    return $entries.ToArray()
}

function Load-Manifest {
    param([string]$Path)
    $result = [pscustomobject]@{
        Headers = @{}
        Entries = @()
        ByName = @{}
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $result
    }
    $lines = Get-Content -LiteralPath $Path -Encoding UTF8
    $inBody = $false
    $entries = New-Object System.Collections.Generic.List[object]
    foreach ($line in $lines) {
        if ($line -eq 'kind	name	source_rel	target_rel	mode') {
            $inBody = $true
            continue
        }
        if (-not $inBody) {
            $parts = $line -split "`t", 2
            if ($parts.Count -eq 2) {
                $result.Headers[$parts[0]] = $parts[1]
            }
            continue
        }
        $fields = $line -split "`t"
        if ($fields.Count -ne 5) { continue }
        $entry = [pscustomobject]@{
            Kind = $fields[0]
            Name = $fields[1]
            SourceRel = $fields[2]
            TargetRel = $fields[3]
            Mode = $fields[4]
        }
        $entries.Add($entry)
        $result.ByName[$entry.Name] = $entry
    }
    if ($result.Headers.ContainsKey('version') -and $result.Headers['version'] -ne $ManifestVersion) {
        Die "manifest version mismatch in $Path"
    }
    $result.Entries = $entries.ToArray()
    return $result
}

function Test-NameInReplaceList {
    param([string]$Name)
    return $ReplaceLink -contains $Name
}

function Compute-Plan {
    param($Inventory, $Manifest, $Config, [string]$ProjectRoot, [string]$ManifestPath)
    $plan = New-Object System.Collections.Generic.List[object]
    $targetRoot = Join-Path $ProjectRoot $Config.TargetRel

    foreach ($entry in $Inventory) {
        $targetPath = Join-Path $targetRoot $entry.Name
        $item = Get-PathItem $targetPath
        $inManifest = $Manifest.ByName.ContainsKey($entry.Name)

        if ($null -eq $item) {
            $action = 'CREATE'
            $extra = ''
        } elseif (Test-LinkItem $item) {
            $currentTarget = Get-LinkTarget $targetPath
            if (Same-Path $currentTarget $entry.ExpectedTarget) {
                $action = $(if ($inManifest) { 'REUSE' } else { 'ADOPT' })
                $extra = ''
            } elseif (($inManifest -or (Test-NameInReplaceList $entry.Name)) -and (Test-ResolvedPathInside $currentTarget $Config.RepoRoot)) {
                $action = 'UPDATE_TARGET'
                $extra = $currentTarget
            } else {
                $action = 'CONFLICT'
                $extra = "link_to:$currentTarget"
            }
        } else {
            $action = 'CONFLICT'
            $extra = 'real_path'
        }

        $plan.Add([pscustomobject]@{
            Action = $action
            Kind = $entry.Kind
            Name = $entry.Name
            SourceRel = $entry.SourceRel
            TargetRel = $entry.TargetRel
            ExpectedTarget = $entry.ExpectedTarget
            TargetPath = $targetPath
            Extra = $extra
        })
    }

    $inventoryNames = @{}
    foreach ($entry in $Inventory) {
        $inventoryNames[$entry.Name] = $true
    }
    $recordedRepo = ''
    if ($Manifest.Headers.ContainsKey('repo_root')) {
        $recordedRepo = $Manifest.Headers['repo_root']
    }
    foreach ($entry in $Manifest.Entries) {
        if ($inventoryNames.ContainsKey($entry.Name)) {
            continue
        }
        if (-not $recordedRepo) {
            Die "manifest missing repo_root: $ManifestPath"
        }
        $plan.Add([pscustomobject]@{
            Action = 'REMOVE'
            Kind = $entry.Kind
            Name = $entry.Name
            SourceRel = $entry.SourceRel
            TargetRel = $entry.TargetRel
            ExpectedTarget = (Join-RelativePath $recordedRepo $entry.SourceRel)
            TargetPath = (Join-RelativePath $ProjectRoot $entry.TargetRel)
            Extra = (Join-RelativePath $recordedRepo $entry.SourceRel)
        })
    }
    return $plan.ToArray()
}

function Print-Plan {
    param($Plan, [string]$Mode)
    Write-Host ''
    Write-Host "ARIS Windows Install Plan"
    Write-Host "  Mode: $Mode"
    foreach ($action in @('CREATE', 'ADOPT', 'UPDATE_TARGET', 'REUSE', 'REMOVE', 'CONFLICT')) {
        $count = @($Plan | Where-Object { $_.Action -eq $action }).Count
        Write-Host ("  {0}: {1}" -f $action, $count)
    }
    $conflicts = @($Plan | Where-Object { $_.Action -eq 'CONFLICT' })
    if ($conflicts.Count -gt 0) {
        Write-Host ''
        Write-Host 'CONFLICT entries:'
        foreach ($item in $conflicts) {
            Write-Host "  - $($item.Name): $($item.Extra)"
        }
    }
}

function Check-NoSymlinkedParents {
    param([string[]]$Paths)
    foreach ($path in $Paths) {
        $item = Get-PathItem $path
        if (Test-LinkItem $item) {
            Die "$path is a link; refusing to mutate linked parent directories"
        }
    }
}

function Test-ActiveLock {
    param([string]$LockPath)
    $pidPath = Join-Path $LockPath 'owner.pid'
    $hostPath = Join-Path $LockPath 'owner.host'
    if (-not (Test-Path -LiteralPath $pidPath) -or -not (Test-Path -LiteralPath $hostPath)) {
        return $false
    }
    $ownerPid = (Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    $ownerHost = (Get-Content -LiteralPath $hostPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($ownerHost -ne [Environment]::MachineName) {
        return $false
    }
    $pidNumber = 0
    if (-not [int]::TryParse($ownerPid, [ref]$pidNumber)) {
        return $false
    }
    return $null -ne (Get-Process -Id $pidNumber -ErrorAction SilentlyContinue)
}

function Acquire-Lock {
    param([string]$ArisDir, [string]$LockPath)
    if ($DryRun) { return }
    New-Item -ItemType Directory -Force -Path $ArisDir | Out-Null
    try {
        New-Item -ItemType Directory -Path $LockPath -ErrorAction Stop | Out-Null
    } catch {
        if (-not $ClearStaleLock) {
            Die "installer lock exists at $LockPath; rerun with -ClearStaleLock if no install is running"
        }
        if (Test-ActiveLock $LockPath) {
            Die "installer lock at $LockPath belongs to a running process"
        }
        Remove-Item -LiteralPath $LockPath -Recurse -Force
        New-Item -ItemType Directory -Path $LockPath -ErrorAction Stop | Out-Null
    }
    Write-Text (Join-Path $LockPath 'owner.pid') "$PID`n"
    Write-Text (Join-Path $LockPath 'owner.host') "$([Environment]::MachineName)`n"
    Write-Text (Join-Path $LockPath 'owner.json') "{`"host`":`"$([Environment]::MachineName)`",`"pid`":$PID,`"tool`":`"install_aris.ps1`"}`n"
    $script:LockDir = $LockPath
    $script:LockAcquired = $true
}

function Release-Lock {
    if (-not $script:LockAcquired -or -not $script:LockDir) { return }
    Remove-Item -LiteralPath $script:LockDir -Recurse -Force -ErrorAction SilentlyContinue
}

function New-Junction {
    param([string]$Path, [string]$Target)
    New-Item -ItemType Junction -Path $Path -Target $Target | Out-Null
}

function Remove-LinkPath {
    param([string]$Path)
    [System.IO.Directory]::Delete($Path, $false)
}

function Get-LegacyState {
    param($Config, [string]$ProjectRoot)
    $path = Join-Path $ProjectRoot $Config.LegacyNestedRel
    $item = Get-PathItem $path
    if ($null -eq $item) {
        return [pscustomobject]@{ Kind = 'none'; Path = $path; Target = '' }
    }
    if (Test-LinkItem $item) {
        $target = Get-LinkTarget $path
        if (Same-Path $target $Config.SourceRoot) {
            return [pscustomobject]@{ Kind = 'link_to_repo'; Path = $path; Target = $target }
        }
        return [pscustomobject]@{ Kind = 'link_to_other'; Path = $path; Target = $target }
    }
    if ($item.PSIsContainer) {
        return [pscustomobject]@{ Kind = 'real_dir'; Path = $path; Target = '' }
    }
    return [pscustomobject]@{ Kind = 'real_file'; Path = $path; Target = '' }
}

function Assert-LegacyMigrationAllowed {
    param($Legacy)
    if ($Legacy.Kind -eq 'none') { return }
    if (-not $FromOld) {
        Die "legacy nested install detected at $($Legacy.Path); rerun with -FromOld to migrate"
    }
    switch ($Legacy.Kind) {
        'link_to_repo' { return }
        'link_to_other' { Die "legacy nested link points outside expected ARIS source: $($Legacy.Path) -> $($Legacy.Target)" }
        'real_file' { Die "legacy nested path is a real file; move it manually before installing: $($Legacy.Path)" }
        'real_dir' {
            if (-not $MigrateCopy) {
                Die "legacy nested copy detected at $($Legacy.Path); pass -MigrateCopy keep-user or -MigrateCopy prefer-upstream"
            }
            return
        }
    }
}

function Apply-LegacyMigration {
    param($Legacy, [string]$ArisDir)
    if ($Legacy.Kind -eq 'none') { return }
    if ($Legacy.Kind -eq 'link_to_repo') {
        if ($DryRun) {
            Write-Host "  (dry-run) remove legacy nested link $($Legacy.Path)"
        } else {
            Remove-LinkPath $Legacy.Path
            Write-Host "  - legacy nested link"
        }
    }
}

function Archive-LegacyCopy {
    param($Legacy, [string]$ArisDir)
    if ($Legacy.Kind -ne 'real_dir' -or $MigrateCopy -ne 'prefer-upstream') { return }
    if ($DryRun) {
        Write-Host "  (dry-run) archive legacy nested copy $($Legacy.Path)"
        return
    }
    New-Item -ItemType Directory -Force -Path $ArisDir | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    $archive = Join-Path $ArisDir "legacy-copy-backup-$stamp"
    Move-Item -LiteralPath $Legacy.Path -Destination $archive
    Write-Host "  - archived legacy nested copy to $archive"
}

function Ensure-ToolsJunction {
    param([string]$ArisDir, [string]$RepoRoot)
    $linkPath = Join-Path $ArisDir 'tools'
    $expectedTarget = Join-Path $RepoRoot 'tools'
    if (-not (Test-Path -LiteralPath $expectedTarget -PathType Container)) {
        Write-Warning "ARIS tools directory not found: $expectedTarget"
        return
    }
    $item = Get-PathItem $linkPath
    if (Test-LinkItem $item) {
        $currentTarget = Get-LinkTarget $linkPath
        if (Same-Path $currentTarget $expectedTarget) { return }
        Write-Warning ".aris\tools already points to $currentTarget; leaving it unchanged"
        return
    }
    if ($null -ne $item) {
        Write-Warning ".aris\tools already exists as a real path; leaving it unchanged"
        return
    }
    if ($DryRun) {
        Write-Host "  (dry-run) junction $linkPath -> $expectedTarget"
        return
    }
    New-Item -ItemType Directory -Force -Path $ArisDir | Out-Null
    New-Junction $linkPath $expectedTarget
    Write-Host "  + .aris\tools"
}

function Remove-ToolsJunction {
    param([string]$ArisDir, [string]$RepoRoot, [string]$CurrentManifestName = '')
    $linkPath = Join-Path $ArisDir 'tools'
    $expectedTarget = Join-Path $RepoRoot 'tools'
    $item = Get-PathItem $linkPath
    if (-not (Test-LinkItem $item)) { return }
    $currentTarget = Get-LinkTarget $linkPath
    if (-not (Same-Path $currentTarget $expectedTarget)) { return }
    foreach ($manifestName in @('installed-skills.txt', 'installed-skills-codex.txt')) {
        if ($manifestName -eq $CurrentManifestName) { continue }
        $otherManifestPath = Join-Path $ArisDir $manifestName
        if (-not (Test-Path -LiteralPath $otherManifestPath -PathType Leaf)) { continue }
        $otherManifest = Load-Manifest $otherManifestPath
        if ($otherManifest.Headers.ContainsKey('repo_root') -and (Same-Path $otherManifest.Headers['repo_root'] $RepoRoot)) {
            Write-Host "  = .aris\tools (kept; $manifestName still uses this ARIS repo)"
            return
        }
    }
    if ($DryRun) {
        Write-Host "  (dry-run) remove $linkPath"
    } else {
        Remove-LinkPath $linkPath
        Write-Host "  - .aris\tools"
    }
}

function Apply-Plan {
    param($Plan, [string]$RepoRoot)
    foreach ($entry in $Plan) {
        switch ($entry.Action) {
            'REUSE' { continue }
            'ADOPT' { continue }
            'CREATE' {
                if ($DryRun) {
                    Write-Host "  (dry-run) junction $($entry.TargetPath) -> $($entry.ExpectedTarget)"
                    continue
                }
                if (Get-PathItem $entry.TargetPath) {
                    Die "path appeared during install: $($entry.TargetPath)"
                }
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $entry.TargetPath) | Out-Null
                New-Junction $entry.TargetPath $entry.ExpectedTarget
                Write-Host "  + $($entry.Name)"
            }
            'UPDATE_TARGET' {
                if ($DryRun) {
                    Write-Host "  (dry-run) relink $($entry.TargetPath) -> $($entry.ExpectedTarget)"
                    continue
                }
                $currentTarget = Get-LinkTarget $entry.TargetPath
                if (-not (Same-Path $currentTarget $entry.Extra)) {
                    Die "link target changed during install for $($entry.Name)"
                }
                if (-not (Test-ResolvedPathInside $currentTarget $RepoRoot)) {
                    Die "refusing to relink $($entry.Name); current target is outside ARIS repo: $currentTarget"
                }
                Remove-LinkPath $entry.TargetPath
                New-Junction $entry.TargetPath $entry.ExpectedTarget
                Write-Host "  > $($entry.Name)"
            }
            'REMOVE' {
                $item = Get-PathItem $entry.TargetPath
                if ($null -eq $item) {
                    Write-Host "  - $($entry.Name) (already absent)"
                    continue
                }
                if (-not (Test-LinkItem $item)) {
                    Write-Warning "skipping $($entry.Name); target is no longer a junction/symlink"
                    continue
                }
                $currentTarget = Get-LinkTarget $entry.TargetPath
                if (-not (Same-Path $currentTarget $entry.Extra)) {
                    Write-Warning "skipping $($entry.Name); target changed to $currentTarget"
                    continue
                }
                if ($DryRun) {
                    Write-Host "  (dry-run) remove $($entry.TargetPath)"
                } else {
                    Remove-LinkPath $entry.TargetPath
                    Write-Host "  - $($entry.Name)"
                }
            }
            'CONFLICT' {
                Die "conflict reached apply phase for $($entry.Name)"
            }
        }
    }
}

function New-ManifestContent {
    param($Plan, [string]$RepoRoot, [string]$ProjectRoot, [string]$PlatformName)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("version`t$ManifestVersion")
    $lines.Add("repo_root`t$RepoRoot")
    $lines.Add("project_root`t$ProjectRoot")
    $lines.Add("platform`t$PlatformName")
    $lines.Add("generated`t$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))")
    $lines.Add("kind`tname`tsource_rel`ttarget_rel`tmode")
    foreach ($entry in $Plan | Where-Object { $_.Action -in @('REUSE', 'ADOPT', 'CREATE', 'UPDATE_TARGET') } | Sort-Object Name) {
        $lines.Add("$($entry.Kind)`t$($entry.Name)`t$($entry.SourceRel)`t$($entry.TargetRel)`tjunction")
    }
    return ($lines -join "`n") + "`n"
}

function Commit-Manifest {
    param([string]$ManifestPath, [string]$ManifestPrevPath, [string]$Content)
    if ($DryRun) {
        Write-Host "  (dry-run) would commit manifest $ManifestPath"
        return
    }
    $manifestDir = Split-Path -Parent $ManifestPath
    New-Item -ItemType Directory -Force -Path $manifestDir | Out-Null
    $tmp = "$ManifestPath.tmp.$PID"
    Write-Text $tmp $Content
    if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
        Copy-Item -LiteralPath $ManifestPath -Destination "$ManifestPrevPath.tmp" -Force
        Move-Item -LiteralPath "$ManifestPrevPath.tmp" -Destination $ManifestPrevPath -Force
    }
    Move-Item -LiteralPath $tmp -Destination $ManifestPath -Force
}

function Update-ManagedDoc {
    param($Config, [string]$DocPath, [string]$RepoRoot, [string]$ProjectRoot, [int]$Count)
    if ($NoDoc) { return }
    $reconcileCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\tools\install_aris.ps1`" `"$ProjectRoot`" -Platform $($Config.Platform) -Reconcile"
    $block = @"
$($Config.BlockBegin)
## $($Config.Title)
ARIS skills installed in this project: $Count entries.
Manifest: ``.aris/$($Config.ManifestName)``
ARIS repo root: ``$RepoRoot``
Project skill path: ``$($Config.TargetRelDisplay)/<skill-name>``
For ARIS workflows, prefer the project-local skills under ``$($Config.TargetRelDisplay)/``.
Do not edit or delete junctioned skills in place; update upstream or rerun:
``$reconcileCommand``
$($Config.BlockEnd)
"@
    $original = ''
    if (Test-Path -LiteralPath $DocPath -PathType Leaf) {
        $original = Read-Text $DocPath
    }
    $newContent = $null
    if ($original.Contains($Config.BlockBegin)) {
        $pattern = [regex]::Escape($Config.BlockBegin) + '.*?' + [regex]::Escape($Config.BlockEnd)
        $newContent = [regex]::Replace(
            $original,
            $pattern,
            [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $block },
            [System.Text.RegularExpressions.RegexOptions]::Singleline
        )
    } else {
        $separator = ''
        if ($original.Length -gt 0 -and -not $original.EndsWith("`n")) {
            $separator = "`n"
        }
        $newContent = $original + $separator + $block + "`n"
    }
    Write-Text $DocPath $newContent
}

function Remove-ManagedDocBlock {
    param($Config, [string]$DocPath)
    if ($NoDoc -or -not (Test-Path -LiteralPath $DocPath -PathType Leaf)) { return }
    if ($DryRun) {
        Write-Host "  (dry-run) would remove managed block from $DocPath"
        return
    }
    $original = Read-Text $DocPath
    if (-not $original.Contains($Config.BlockBegin)) { return }
    $pattern = "`r?`n?" + [regex]::Escape($Config.BlockBegin) + '.*?' + [regex]::Escape($Config.BlockEnd) + "`r?`n?"
    $newContent = [regex]::Replace(
        $original,
        $pattern,
        [System.Text.RegularExpressions.MatchEvaluator]{ param($m) "`n" },
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    ).TrimStart("`r", "`n")
    Write-Text $DocPath $newContent
}

function Do-Uninstall {
    param($Config, [string]$ProjectRoot, [string]$ManifestPath, [string]$ManifestPrevPath, [string]$DocPath)
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Die "no manifest at $ManifestPath; nothing to uninstall"
    }
    $manifest = Load-Manifest $ManifestPath
    if (-not $manifest.Headers.ContainsKey('repo_root')) {
        Die "manifest missing repo_root: $ManifestPath"
    }
    $recordedRepo = $manifest.Headers['repo_root']
    Write-Host ''
    Write-Host 'Uninstall plan:'
    foreach ($entry in $manifest.Entries) {
        Write-Host "  - $($entry.Name) ($($entry.Kind))"
    }
    foreach ($entry in $manifest.Entries) {
        $targetPath = Join-RelativePath $ProjectRoot $entry.TargetRel
        $expectedTarget = Join-RelativePath $recordedRepo $entry.SourceRel
        $item = Get-PathItem $targetPath
        if ($null -eq $item) { continue }
        if (-not (Test-LinkItem $item)) {
            Write-Warning "skipping $($entry.Name); target path is not a junction/symlink"
            continue
        }
        $currentTarget = Get-LinkTarget $targetPath
        if (Same-Path $currentTarget $expectedTarget) {
            if ($DryRun) {
                Write-Host "  (dry-run) remove $targetPath"
            } else {
                Remove-LinkPath $targetPath
                Write-Host "  - removed $($entry.Name)"
            }
        } else {
            Write-Warning "skipping $($entry.Name); target changed to $currentTarget"
        }
    }
    Remove-ToolsJunction (Split-Path -Parent $ManifestPath) $recordedRepo $Config.ManifestName
    if (-not $DryRun) {
        Move-Item -LiteralPath $ManifestPath -Destination $ManifestPrevPath -Force
    }
    Remove-ManagedDocBlock $Config $DocPath
}

function Invoke-Main {
    if ($Force) {
        Die '-Force is no longer supported. Use -ReplaceLink NAME for a specific existing junction/symlink; real files are never overwritten.'
    }
    if ($Reconcile -and $Uninstall) {
        Die '-Reconcile and -Uninstall are mutually exclusive'
    }
    if ($All -and (Get-CommaList $Groups).Count + (Get-CommaList $Skills).Count -gt 0) {
        Die '-All cannot be combined with -Groups/-Skills (only -Exclude)'
    }
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        Die "project path does not exist: $ProjectPath"
    }
    $projectRoot = (Resolve-Path -LiteralPath $ProjectPath).ProviderPath
    $repoRoot = Resolve-ArisRepo
    $catalog = Load-Catalog (Join-RelativePath $repoRoot $CatalogRel)
    if ($ListGroups) {
        Show-GroupCatalog $catalog
        return
    }
    $selectedPlatform = $Platform
    if ($selectedPlatform -eq 'auto') {
        $selectedPlatform = Detect-Platform $projectRoot
    }
    $config = New-Config $projectRoot $repoRoot $selectedPlatform
    $arisDir = Join-Path $projectRoot '.aris'
    $manifestPath = Join-Path $arisDir $config.ManifestName
    $manifestPrevPath = Join-Path $arisDir $config.ManifestPrevName
    $docPath = Join-Path $projectRoot $config.DocName
    $targetRoot = Join-Path $projectRoot $config.TargetRel
    $lockPath = Join-Path $arisDir $config.LockName
    $mode = $(if ($DryRun) { 'DRY-RUN' } elseif ($Uninstall) { 'UNINSTALL' } elseif ($Reconcile) { 'RECONCILE' } else { 'APPLY' })

    Write-Host ''
    Write-Host 'ARIS Project Install'
    Write-Host "  Project:  $projectRoot"
    Write-Host "  Platform: $selectedPlatform"
    Write-Host "  Repo:     $repoRoot"
    Write-Host "  Target:   $targetRoot"
    Write-Host "  Mode:     $mode"

    Check-NoSymlinkedParents @($arisDir, (Split-Path -Parent $targetRoot), $targetRoot)

    if ($Uninstall) {
        if (-not $DryRun) { Acquire-Lock $arisDir $lockPath }
        Do-Uninstall $config $projectRoot $manifestPath $manifestPrevPath $docPath
        return
    }

    $legacy = Get-LegacyState $config $projectRoot
    Assert-LegacyMigrationAllowed $legacy

    if ($Reconcile -and -not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Die "-Reconcile requires existing manifest; none found at $manifestPath"
    }

    $inventory = Build-Inventory $config
    $manifest = Load-Manifest $manifestPath

    # Selective install (#366 parity): build the selected set, then plan
    # against that filtered subset (support entries always pass through).
    $upstreamSkillNames = New-Object System.Collections.Generic.HashSet[string]
    foreach ($entry in $inventory) {
        if ($entry.Kind -eq 'skill') { $upstreamSkillNames.Add($entry.Name) | Out-Null }
    }
    $isFresh = -not (Test-Path -LiteralPath $manifestPath -PathType Leaf)
    $declinedPath = Join-Path $arisDir $config.DeclinedName
    $selection = Build-Selection $catalog $manifest $upstreamSkillNames $declinedPath $isFresh
    $selectedInventory = @($inventory | Where-Object { $_.Kind -eq 'support' -or $selection.Selected.Contains($_.Name) })
    Write-Host ''
    Write-Host "Selection: $($selection.Selected.Count) of $($upstreamSkillNames.Count) upstream skills"

    $plan = Compute-Plan $selectedInventory $manifest $config $projectRoot $manifestPath
    Print-Plan $plan $mode

    $conflicts = @($plan | Where-Object { $_.Action -eq 'CONFLICT' })
    if ($conflicts.Count -gt 0) {
        Die "CONFLICT: $($conflicts.Count) existing path(s) must be resolved before install"
    }

    if ($DryRun) {
        Apply-LegacyMigration $legacy $arisDir
        Archive-LegacyCopy $legacy $arisDir
        Ensure-ToolsJunction $arisDir $repoRoot
        Write-Host ''
        Write-Host '(dry-run) no changes made'
        return
    }

    Acquire-Lock $arisDir $lockPath
    Apply-LegacyMigration $legacy $arisDir
    New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
    Write-Host ''
    Write-Host 'Applying:'
    Apply-Plan $plan $repoRoot
    $manifestContent = New-ManifestContent $plan $repoRoot $projectRoot $selectedPlatform
    Commit-Manifest $manifestPath $manifestPrevPath $manifestContent
    Ensure-ToolsJunction $arisDir $repoRoot
    Archive-LegacyCopy $legacy $arisDir

    # #366: persist declined skills + global repo pointer (both best-effort,
    # after manifest commit for the same reason as the tools junction above).
    Save-DeclinedSet $declinedPath $selection.DeclinedCandidates $selection.Selected
    Ensure-GlobalPointer $repoRoot

    $managedCount = @($plan | Where-Object { $_.Action -in @('REUSE', 'ADOPT', 'CREATE', 'UPDATE_TARGET') }).Count
    Update-ManagedDoc $config $docPath $repoRoot $projectRoot $managedCount
    Write-Host ''
    Write-Host "Install complete. Managed entries: $managedCount"
}

$exitCode = 0
try {
    Invoke-Main
} catch {
    Write-Error $_.Exception.Message
    $exitCode = 1
} finally {
    Release-Lock
}
exit $exitCode
