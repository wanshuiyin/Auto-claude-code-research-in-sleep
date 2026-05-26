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

    # Kept only to preserve CLI recognition. It is intentionally unsafe for
    # this installer and is rejected in favor of per-skill -ReplaceLink.
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$ManifestVersion = '1'
$SafeNameRegex = '^[A-Za-z0-9][A-Za-z0-9._-]*$'
$SupportNames = @('shared-references')
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
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        Die "project path does not exist: $ProjectPath"
    }
    $projectRoot = (Resolve-Path -LiteralPath $ProjectPath).ProviderPath
    $repoRoot = Resolve-ArisRepo
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
    $plan = Compute-Plan $inventory $manifest $config $projectRoot $manifestPath
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
