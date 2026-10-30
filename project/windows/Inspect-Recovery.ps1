# SPDX-License-Identifier: MIT
# Read-only recovery inspection. Never invokes or modifies files on the card.
param([switch]$LibraryOnly)
$script:RecoveryRunInteractive = -not $LibraryOnly
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'TrimUI-Card-Helper.ps1') -LibraryOnly

function Read-RecoveryFile([string]$Path, [long]$Limit = 262144) {
    Assert-NoLinks $Path
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.PSIsContainer -or $item.Length -gt $Limit) { throw 'Recovery candidate is not a bounded regular file.' }
    $stream = $null; $hash = $null
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $bytes = New-Object byte[] ([int]$item.Length)
        $offset = 0
        while ($offset -lt $bytes.Length) {
            $read = $stream.Read($bytes, $offset, $bytes.Length - $offset)
            if ($read -le 0) { throw 'Candidate changed during read.' }
            $offset += $read
        }
        if ($stream.ReadByte() -ne -1) { throw 'Candidate grew during read.' }
        $after = Get-Item -LiteralPath $Path -Force
        if ($after.Length -ne $item.Length -or $after.LastWriteTimeUtc.Ticks -ne $item.LastWriteTimeUtc.Ticks) { throw 'Candidate changed during read.' }
        Assert-NoLinks $Path
        $hash = [Security.Cryptography.SHA256]::Create()
        $sha = [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
        $text = (New-Object Text.UTF8Encoding($false,$true)).GetString($bytes).TrimStart([char]0xFEFF)
        return [pscustomobject]@{bytes=$bytes.Length; sha256=$sha; text=$text}
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
        if ($null -ne $hash) { $hash.Dispose() }
    }
}
function Get-RecoveryIniSummary([string]$Text, [string]$Kind) {
    $section = ''
    $selected = [ordered]@{}
    $duplicates = @()
    foreach ($line in ($Text -split "`r?`n")) {
        if ($line -match '^\s*\[([^\]]+)\]\s*$') { $section = $Matches[1]; continue }
        if ($line -notmatch '^\s*([^;#=]+?)\s*=\s*(.*?)\s*$') { continue }
        $key = $Matches[1].Trim(); $value = $Matches[2].Trim()
        $allowed = ($Kind -eq 'controls' -and $section -eq 'ControlMapping' -and $key -in @('Cross','Circle','Pause','Start','Select','Up','Down','Left','Right'))
        $allowed = $allowed -or ($Kind -eq 'settings' -and (($section -eq 'General' -and $key -in @('AutoRun','AutoLoadSaveState')) -or ($section -eq 'SystemParam' -and $key -eq 'ButtonPreference')))
        if (-not $allowed) { continue }
        $id = $section + '.' + $key
        if ($selected.Contains($id)) { $duplicates += $id; $selected[$id] = 'duplicate-key-review-required'; continue }
        if ($Kind -eq 'controls') {
            if ($value -eq '') { $selected[$id] = 'empty-binding' }
            elseif ($value -match '^\d+-\d+(\s*,\s*\d+-\d+)*$') { $selected[$id] = $value -replace '\s','' }
            else { $selected[$id] = 'unrecognized-binding-format-value-withheld' }
        } elseif ($value -match '^(True|False|[0-9]{1,3})$') { $selected[$id] = $value }
        else { $selected[$id] = 'unrecognized-value-withheld' }
    }
    if ($Kind -eq 'controls') {
        foreach ($key in @('Cross','Circle','Pause')) {
            $id = 'ControlMapping.' + $key
            if (-not $selected.Contains($id)) { $selected[$id] = 'not-explicitly-present-defaults-not-determined' }
        }
    }
    return [ordered]@{selected=$selected; duplicate_keys=$duplicates; effective_runtime_bindings_verified=$false}
}
function Get-RecoveryCandidates([string]$Source) {
    $systems = New-Object 'System.Collections.Generic.List[string]'
    foreach ($relative in @('.config/ppsspp/PSP/SYSTEM','Emus/PPSSPP/.config/ppsspp/PSP/SYSTEM','Emus/PSP/.config/ppsspp/PSP/SYSTEM','Emu/PSP/.config/ppsspp/PSP/SYSTEM','Saves/.config/ppsspp/PSP/SYSTEM')) { $systems.Add($relative) }
    $crossmix = Join-Path $Source 'Emus/PSP'
    if (Test-Path -LiteralPath $crossmix) {
        Assert-NoLinks $crossmix
        $versions = @(Get-ChildItem -LiteralPath $crossmix -Directory -Force | Where-Object { $_.Name -match '^PPSSPP_[0-9.]+$' })
        if ($versions.Count -gt 32) { throw 'Too many version directories; inspect manually.' }
        foreach ($version in $versions) {
            Assert-NoLinks $version.FullName
            $systems.Add('Emus/PSP/' + $version.Name + '/.config/ppsspp/PSP/SYSTEM')
        }
    }
    $candidates = New-Object 'System.Collections.Generic.List[object]'
    foreach ($system in $systems) {
        foreach ($name in @('controls.ini','controls-SmartPro.ini','ppsspp.ini','ppsspp-SmartPro.ini')) {
            $kind = 'settings'; if ($name.StartsWith('controls')) { $kind = 'controls' }
            $candidates.Add([pscustomobject]@{path=$system+'/'+$name;kind=$kind})
        }
    }
    foreach ($pair in @(@('System/etc/crossmix.json','crossmix'),@('spruce/flags/save_active.lock','marker'),@('spruce/flags/lastgame.lock','marker'),@('spruce/scripts/runtime.sh','script'),@('spruce/scripts/emu/lib/ppsspp_functions.sh','script'))) {
        $candidates.Add([pscustomobject]@{path=$pair[0];kind=$pair[1]})
    }
    return $candidates.ToArray()
}
function Invoke-RecoveryInspection([string]$Source, [string]$OutputParent) {
    Assert-NoLinks $Source
    if (-not (Get-Item -LiteralPath $Source -Force).PSIsContainer) { throw 'Choose the card root or backed-up card-files folder.' }
    $findings = New-Object 'System.Collections.Generic.List[object]'
    foreach ($candidate in @(Get-RecoveryCandidates $Source)) {
        $path = Join-Path $Source $candidate.path
        if (-not (Test-Path -LiteralPath $path)) { continue }
        # Refuse links, unreadable/malformed or changing files, rather than emit a success report.
        $read = Read-RecoveryFile $path
        $summary = $null
        if ($candidate.kind -in @('controls','settings')) { $summary = Get-RecoveryIniSummary $read.text $candidate.kind }
        elseif ($candidate.kind -eq 'crossmix') {
            $value = $read.text | ConvertFrom-Json
            $property = $value.PSObject.Properties['RESUME AT BOOT']
            $state = 'not-present'
            if ($null -ne $property) {
                if ($property.Value -is [int] -or $property.Value -is [long]) {
                    if ($property.Value -in @(0,1)) { $state = [string]$property.Value } else { $state = 'unrecognized-value-withheld' }
                } else { $state = 'unrecognized-value-withheld' }
            }
            $summary = [ordered]@{resume_at_boot=$state; actual_startup_owner_verified=$false}
        }
        $findings.Add([pscustomobject]@{path=$candidate.path;kind=$candidate.kind;bytes=$read.bytes;sha256=$read.sha256;summary=$summary})
    }
    $report = [ordered]@{
        schema=1; operation='read-only PPSSPP recovery inspection'; utc=[DateTime]::UtcNow.ToString('o')
        findings=$findings.ToArray(); source_modified=$false; repair_applied=$false
        model_verified=$false; effective_runtime_verified=$false; custom_os_installed=$false
        limits=@('Candidates are not proof of which PPSSPP build is active.','Missing explicit bindings may use defaults.','AutoRun is a PPSSPP setting, not proof of OS boot autostart.','No per-game configurations, ROMs, saves, recent game paths or credentials are emitted.','spruce can overwrite controls.ini from controls-SmartPro.ini at launch.','Unknown startup hooks and internal firmware were not scanned.')
        next_step='After a verified full backup, review this report and actual launcher identity before selecting a reversible repair. No reset or rename is performed.'
    }
    $run = New-RunDirectory $Source $OutputParent
    Write-PrivateJson (Join-Path $run 'recovery-inspection.json') $report
    Write-Host "Recovery inspection saved: $run"
    Write-Host 'The source card/backup was not modified. This report contains only selected setting values and known relative paths.'
    return $run
}
function Start-RecoveryInspection {
    if ($env:OS -ne 'Windows_NT') { throw 'Use the interactive helper on Windows.' }
    Write-Host 'Inspect PPSSPP controls and known boot-resume clues (read-only)' -ForegroundColor Cyan
    Write-Host 'Use the card through a reader, or the card-files folder in your verified laptop backup.'
    $source = (Read-Host 'Card root or card-files folder, for example E:\').Trim().Trim('"')
    $default = [Environment]::GetFolderPath('MyDocuments')
    $parent = (Read-Host "Laptop report folder (Enter for $default)").Trim().Trim('"')
    if ($parent -eq '') { $parent = $default }
    [void](Invoke-RecoveryInspection $source $parent)
}
if ($script:RecoveryRunInteractive) {
    try { Start-RecoveryInspection; exit 0 }
    catch { Write-Host "Stopped: $($_.Exception.Message)" -ForegroundColor Red; Write-Host 'No repair or source modification was performed.'; exit 1 }
}
