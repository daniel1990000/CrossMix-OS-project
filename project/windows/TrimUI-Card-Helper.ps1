# Requires Windows PowerShell 5.1 for the interactive helper.
# No network, card writes, format, delete, save conversion or device activation.
param([switch]$LibraryOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
}
function Test-Within([string]$Child, [string]$Parent) {
    return (Get-FullPath $Child).StartsWith((Get-FullPath $Parent), [StringComparison]::OrdinalIgnoreCase)
}
function Assert-NoLinks([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $node = Get-Item -LiteralPath $full -Force
    while ($null -ne $node) {
        if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Link/junction refused: $($node.FullName)"
        }
        if ($node -is [IO.FileInfo]) { $node = $node.Directory } else { $node = $node.Parent }
    }
}
function Get-CardTree([string]$Root) {
    Assert-NoLinks $Root
    $rootPath = Get-FullPath $Root
    $entries = New-Object 'System.Collections.Generic.List[object]'
    $pending = New-Object 'System.Collections.Generic.Stack[System.IO.DirectoryInfo]'
    $pending.Push((Get-Item -LiteralPath $Root -Force))
    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        Assert-NoLinks $dir.FullName
        foreach ($item in $dir.GetFileSystemInfos()) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Link/junction refused: $($item.FullName)"
            }
            $relative = $item.FullName.Substring($rootPath.Length)
            $isDirectory = $item -is [IO.DirectoryInfo]
            $length = 0L
            if (-not $isDirectory) { $length = $item.Length }
            $entries.Add([pscustomobject]@{
                path = $relative; directory = $isDirectory; bytes = $length
                modified_utc_ticks = $item.LastWriteTimeUtc.Ticks
                attributes = [int]$item.Attributes
            })
            if ($entries.Count -gt 250000) { throw 'More than 250,000 entries: use a reviewed disk-image backup.' }
            if ($isDirectory) { $pending.Push($item) }
        }
    }
    return $entries.ToArray() | Sort-Object path
}
function Get-TreeSignature($Entries) {
    # Compare source membership/metadata before and after copying; contents are hashed separately.
    return ($Entries | ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.path, $_.directory, $_.bytes, $_.modified_utc_ticks }) -join "`n"
}
function Get-ByteTotal($Entries) {
    $total = 0L
    foreach ($entry in $Entries) { $total += $entry.bytes }
    return $total
}
function Get-CardSummary($Entries) {
    $files = @($Entries | Where-Object { -not $_.directory })
    $roms = @($files | Where-Object { $_.path -match '^(Roms|ROMS|roms)[\\/]' })
    $bySystem = @($roms | Group-Object { ($_.path -split '[\\/]')[1] } | ForEach-Object {
        [pscustomobject]@{ folder = $_.Name; files = $_.Count; bytes = [long](($_.Group | Measure-Object bytes -Sum).Sum) }
    })
    $saveFolders = @($Entries | Where-Object { $_.directory -and $_.path -match '(^|[\\/])(Saves|saves|states|SAVEDATA|PPSSPP_STATE|memcards|memorycards)$' } | ForEach-Object { $_.path })
    $top = @($Entries | Where-Object { $_.path -notmatch '[\\/]' } | ForEach-Object { $_.path })
    $clues = @()
    if (@($Entries | Where-Object { $_.path -match '^spruce([\\/]|$)' }).Count) { $clues += 'spruce folder present (identity not verified)' }
    if (@($Entries | Where-Object { $_.path -match '^Emus([\\/]|$)' }).Count) { $clues += 'Emus folder present (stock/CrossMix-style layout possible)' }
    if (@($Entries | Where-Object { $_.path -match '^Emu([\\/]|$)' }).Count) { $clues += 'Emu folder present (spruce-style layout possible)' }
    return [ordered]@{
        schema = 1; operation = 'read-only card layout'; utc = [DateTime]::UtcNow.ToString('o')
        files = $files.Count; bytes = (Get-ByteTotal $files)
        top_level_entries = $top; layout_clues = $clues; rom_folders = $bySystem
        rom_extensions = @($roms | Group-Object { [IO.Path]::GetExtension($_.path).ToLowerInvariant() } | ForEach-Object { [pscustomobject]@{extension=$_.Name; files=$_.Count} })
        possible_save_folders = $saveFolders
        model = 'not established from card layout'; firmware = 'not established'
        save_coverage_verified = $false; hardware_qualified = $false; device_activation = $false
        note = 'Names/counts only. No game, save, configuration or credential contents read. File counts are not game counts. Save folders are clues, not a complete save map.'
    }
}
function Write-PrivateJson([string]$Path, $Value) {
    $text = ConvertTo-Json -InputObject $Value -Depth 12
    [IO.File]::WriteAllText($Path, $text, (New-Object Text.UTF8Encoding($false)))
}
function New-RunDirectory([string]$Source, [string]$Parent) {
    Assert-NoLinks $Source
    Assert-NoLinks $Parent
    if ((Test-Within $Parent $Source) -or (Test-Within $Source $Parent)) {
        throw 'The backup parent and source must be separate, non-overlapping directories.'
    }
    $run = Join-Path $Parent ('TrimUI-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
    if (Test-Path -LiteralPath $run) { throw 'Output already exists.' }
    [void][IO.Directory]::CreateDirectory($run)
    return $run
}
function Copy-VerifiedFile([string]$Source, [string]$Destination, $Entry) {
    Assert-NoLinks $Source
    Assert-NoLinks ([IO.Path]::GetDirectoryName($Destination))
    $before = Get-Item -LiteralPath $Source -Force
    if ($before.Length -ne $Entry.bytes -or $before.LastWriteTimeUtc.Ticks -ne $Entry.modified_utc_ticks) { throw "Source changed before copy: $($Entry.path)" }
    $inputStream = $null; $outputStream = $null; $hash = $null
    try {
        # Share.Read refuses other write/delete handles on Windows while copying/hashing.
        $inputStream = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        $outputStream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $inputStream.CopyTo($outputStream, 1048576)
        $outputStream.Flush($true)
        $outputStream.Dispose(); $outputStream = $null
        $inputStream.Position = 0
        $hash = [Security.Cryptography.SHA256]::Create()
        $sourceHash = [BitConverter]::ToString($hash.ComputeHash($inputStream)).Replace('-','').ToLowerInvariant()
        $copied = Get-Item -LiteralPath $Destination -Force
        $destinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($copied.Length -ne $Entry.bytes -or $sourceHash -ne $destinationHash) { throw "Backup readback mismatch: $($Entry.path)" }
        $after = Get-Item -LiteralPath $Source -Force
        if ($after.Length -ne $Entry.bytes -or $after.LastWriteTimeUtc.Ticks -ne $Entry.modified_utc_ticks) { throw "Source changed during copy: $($Entry.path)" }
        Assert-NoLinks $Source
        [IO.File]::SetLastWriteTimeUtc($Destination, [DateTime]::new($Entry.modified_utc_ticks, [DateTimeKind]::Utc))
        [IO.File]::SetAttributes($Destination, [IO.FileAttributes]$Entry.attributes)
        return [pscustomobject]@{ path=$Entry.path; bytes=$Entry.bytes; sha256=$sourceHash }
    } finally {
        if ($null -ne $inputStream) { $inputStream.Dispose() }
        if ($null -ne $outputStream) { $outputStream.Dispose() }
        if ($null -ne $hash) { $hash.Dispose() }
    }
}
function Invoke-CardBackup([string]$Source, [string]$Parent) {
    $entries = @(Get-CardTree $Source)
    $files = @($entries | Where-Object { -not $_.directory })
    $bytes = (Get-ByteTotal $files)
    $drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Parent)))
    $reserve = [Math]::Max(1073741824L, $bytes * 0.05)
    if ($drive.AvailableFreeSpace -lt ($bytes + $reserve)) { throw 'Not enough free space on backup disk (payload plus 5% or 1 GiB reserve required).' }
    $run = New-RunDirectory $Source $Parent
    $payload = Join-Path $run 'card-files'
    [void][IO.Directory]::CreateDirectory($payload)
    $statusPath = Join-Path $run 'backup-status.json'
    $status = [ordered]@{schema=1; state='incomplete'; source_files=$files.Count; source_bytes=$bytes; verified_files=0; hardware_qualified=$false; physical_restore_tested=$false; internal_storage_backed_up=$false; sector_image=$false; error=$null}
    Write-PrivateJson $statusPath $status
    Write-PrivateJson (Join-Path $run 'card-summary-private.json') (Get-CardSummary $entries)
    $manifest = New-Object 'System.Collections.Generic.List[object]'
    try {
        foreach ($entry in @($entries | Where-Object directory | Sort-Object { $_.path.Length })) {
            [void][IO.Directory]::CreateDirectory((Join-Path $payload $entry.path))
        }
        $count=0
        foreach ($entry in $files) {
            $count++
            Write-Progress -Activity 'Copying and verifying every card file' -Status "$count of $($files.Count) files" -PercentComplete ([int](100 * $count / [Math]::Max(1,$files.Count)))
            $manifest.Add((Copy-VerifiedFile (Join-Path $Source $entry.path) (Join-Path $payload $entry.path) $entry))
        }
        if ((Get-TreeSignature $entries) -cne (Get-TreeSignature @(Get-CardTree $Source))) { throw 'Source tree changed during backup. This backup is not marked verified.' }
        foreach ($entry in @($entries | Where-Object directory | Sort-Object { $_.path.Length } -Descending)) {
            $target = Join-Path $payload $entry.path
            [IO.Directory]::SetLastWriteTimeUtc($target, [DateTime]::new($entry.modified_utc_ticks, [DateTimeKind]::Utc))
            [IO.File]::SetAttributes($target, [IO.FileAttributes]$entry.attributes)
        }
        Write-PrivateJson (Join-Path $run 'files-private.json') $manifest.ToArray()
        $status.state='verified-file-copy'; $status.verified_files=$manifest.Count
        Write-PrivateJson $statusPath $status
        Write-Progress -Activity 'Copying and verifying every card file' -Completed
        Write-Host "`nBACKUP VERIFIED: $run" -ForegroundColor Green
        Write-Host 'Keep the original card intact. A verified file copy does not include internal firmware or prove a spare-card boot/restore.'
        return $run
    } catch {
        $status.state='failed'; $status.verified_files=$manifest.Count; $status.error=$_.Exception.Message
        Write-PrivateJson $statusPath $status
        Write-Host "Partial backup retained at: $run" -ForegroundColor Yellow
        throw
    }
}
function Start-CardHelper {
    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'Use this helper on Windows with PowerShell 5.1 or later.' }
    Write-Host 'TrimUI - preserve your card before the custom PSP interface' -ForegroundColor Cyan
    Write-Host 'Connect through the handheld USB Storage app, or use a card reader.'
    Write-Host 'In USB Storage mode, keep the handheld in that app for the entire copy.'
    Write-Host 'Do not run games, sync or other apps while Windows has the card mounted.'
    Write-Host 'This helper does not install an OS, format a card or move/delete games.'
    Write-Host "`nAvailable drives:"
    Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -match '^[A-Za-z]:\\$' } | Format-Table Name, Root, @{Name='Free GiB';Expression={[Math]::Round($_.Free/1GB,1)}} -AutoSize
    $letter = (Read-Host 'Type the microSD drive letter (for example E)').Trim().TrimEnd(':','\').ToUpperInvariant()
    if ($letter -notmatch '^[A-Z]$') { throw 'Enter exactly one drive letter.' }
    $card = $letter + ':\'
    if ($card.TrimEnd('\') -ieq $env:SystemDrive) { throw 'The Windows system drive cannot be selected as your card.' }
    Assert-NoLinks $card
    $drive = New-Object IO.DriveInfo($card)
    if (-not $drive.IsReady) { throw 'Drive not ready.' }
    Write-Host ("Selected {0}  Label: {1}  Filesystem: {2}  Capacity: {3:N1} GiB" -f $card,$drive.VolumeLabel,$drive.DriveFormat,($drive.TotalSize/1GB))
    if ((Read-Host "Retype $letter to confirm this is the microSD").Trim().ToUpperInvariant() -ne $letter) { throw 'Drive selection cancelled.' }
    Write-Host "`n1 - Inspect card layout only (quick)`n2 - Back up every file and verify it (recommended; may take hours)"
    $choice = (Read-Host 'Choose 1 or 2').Trim()
    if ($choice -notin @('1','2')) { throw 'Cancelled: choose 1 or 2.' }
    $defaultParent = [Environment]::GetFolderPath('MyDocuments')
    if ([string]::IsNullOrWhiteSpace($defaultParent)) { $defaultParent = $env:USERPROFILE }
    $parent = (Read-Host "Laptop folder for backup/report (Enter uses $defaultParent)").Trim().Trim('"')
    if ([string]::IsNullOrWhiteSpace($parent)) { $parent = $defaultParent }
    Assert-NoLinks $parent
    if (-not (Get-Item -LiteralPath $parent -Force).PSIsContainer) { throw 'Choose an existing laptop folder.' }
    if ([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($parent)) -ieq $card) { throw 'The output must be on a different drive from the microSD.' }
    if ($parent.StartsWith('\\')) { throw 'Choose a local laptop disk, not a network share.' }
    if ($choice -eq '2') { [void](Invoke-CardBackup $card $parent) }
    else {
        $entries = @(Get-CardTree $card)
        $run = New-RunDirectory $card $parent
        $summary = Get-CardSummary $entries
        Write-PrivateJson (Join-Path $run 'card-summary-private.json') $summary
        Write-Host "`nRead-only inventory saved: $run" -ForegroundColor Green
        Write-Host ("Files: {0}; total: {1:N1} GiB" -f $summary.files, ($summary.bytes/1GB))
        $summary.rom_folders | Format-Table folder,files -AutoSize
    }
    Write-Host 'Reports and backups stay on your laptop. Review them before sharing; paths may identify games.'
    Write-Host 'When finished: safely eject the drive in Windows, then exit the handheld USB Storage app.'
    Write-Host 'Keep the original card intact. Device installation needs a separate reviewed recovery/test route.'
}
if (-not $LibraryOnly) {
    try { Start-CardHelper; exit 0 }
    catch { Write-Host "`nSTOPPED: $($_.Exception.Message)" -ForegroundColor Red; Write-Host 'This helper did not write to your card. Keep any partial backup; do not treat it as verified.'; exit 1 }
}
