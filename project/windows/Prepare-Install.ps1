# SPDX-License-Identifier: MIT
# Laptop-only preparation. No card deployment, firmware writes or activation.
param([switch]$LibraryOnly)
$script:InstallRunInteractive = -not $LibraryOnly
. (Join-Path $PSScriptRoot 'TrimUI-Card-Helper.ps1') -LibraryOnly

function Get-InstallPin {
    return [pscustomobject]@{
        name='spruceV4.5.4.7z'; bytes=1652634074L
        sha256='4623f1cd824ac1d01e7663d11ca40a8d3ad874c5f071e692f4392957d2159cfd'
        url='https://github.com/spruceUI/spruceOS/releases/download/v4.5.4/spruceV4.5.4.7z'
        source_commit='d45ff8dfe5756147522b04ae5863d17a90e88b54'
    }
}
function Assert-InstallArchive([string]$Path, $Pin) {
    Assert-NoLinks $Path
    $file = Get-Item -LiteralPath $Path -Force
    if ($file.PSIsContainer -or $file.Length -ne $Pin.bytes) { throw 'Base archive size differs from pinned release.' }
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -cne $Pin.sha256) { throw 'Base archive SHA256 differs from pinned release. Nothing extracted.' }
    return $hash
}
function Assert-InstallWorkspace([string]$Path) {
    Assert-NoLinks $Path
    $item=Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) { throw 'Choose an existing laptop folder.' }
    $full=[IO.Path]::GetFullPath($Path)
    if ($env:OS -eq 'Windows_NT') {
        if ($full.StartsWith('\\') -or [IO.Path]::GetPathRoot($full).TrimEnd('\') -ine $env:SystemDrive) {
            throw 'Preparation must be on the Windows system drive, not the microSD or a network share.'
        }
    }
    foreach ($marker in @('Roms','Emu','Emus','spruce')) {
        if (Test-Path -LiteralPath (Join-Path $Path $marker)) { throw 'This resembles a card root. Choose a laptop folder such as Documents.' }
    }
}
function Get-InstallArchive([string]$Workspace, [string]$ExistingArchive='') {
    $pin=Get-InstallPin
    Assert-NoLinks $Workspace
    $target=Join-Path $Workspace $pin.name
    if (Test-Path -LiteralPath $target) {
        [void](Assert-InstallArchive $target $pin)
        return $target
    }
    $partial=$target+'.partial'
    if (Test-Path -LiteralPath $partial) { throw 'An incomplete download already exists. Keep it for inspection; use a new preparation workspace.' }
    if (-not [string]::IsNullOrWhiteSpace($ExistingArchive)) {
        [void](Assert-InstallArchive $ExistingArchive $pin)
        # Copy into a fresh path so the cached owner file remains untouched.
        [IO.File]::Copy([IO.Path]::GetFullPath($ExistingArchive),$partial,$false)
    } else {
        Write-Host 'Downloading the pinned spruce base (about 1.65 GB)...'
        [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
        $client=New-Object Net.WebClient
        try { $client.DownloadFile($pin.url,$partial) } finally { $client.Dispose() }
    }
    [void](Assert-InstallArchive $partial $pin)
    [IO.File]::Move($partial,$target)
    return $target
}
function Find-InstallSevenZip {
    $paths=@()
    foreach ($root in @($env:ProgramFiles,${env:ProgramFiles(x86)})) {
        if (-not [string]::IsNullOrWhiteSpace($root)) { $paths += (Join-Path $root '7-Zip\7z.exe') }
    }
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { Assert-NoLinks $path; return $path }
    }
    return $null
}
function Expand-InstallBase([string]$Archive, [string]$Workspace, [string]$SevenZip) {
    [void](Assert-InstallArchive $Archive (Get-InstallPin))
    Assert-NoLinks $Workspace; Assert-NoLinks $SevenZip
    $destination=Join-Path $Workspace 'pinned-base'
    if (Test-Path -LiteralPath $destination) { throw 'Base output already exists; it will not be overwritten.' }
    [void][IO.Directory]::CreateDirectory($destination)
    $receipt=Join-Path $Workspace 'base-extraction.json'
    Write-PrivateJson $receipt ([ordered]@{state='incomplete';custom_interface_activated=$false;device_ready=$false})
    # A fixed independently pinned archive is verified before any extraction.
    & $SevenZip x $Archive ('-o'+$destination) '-y' '-bd' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "7-Zip extraction failed ($LASTEXITCODE). Partial base retained; do not deploy." }
    Assert-NoLinks $destination
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'App\PyUI\main-ui\mainui.py'))) {
        throw 'Expected pinned spruce root layout missing after extraction. Keep output for inspection; do not deploy.'
    }
    Write-PrivateJson $receipt ([ordered]@{state='base-extracted';archive_sha256=(Get-InstallPin).sha256;custom_interface_activated=$false;device_ready=$false;note='Pinned upstream base only. Custom candidate composition and actual-device review are separate.'})
    return $destination
}
function Test-InstallRelativePath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '^[\\/]' -or $Path -match '[:\x00-\x1f]') { return $false }
    foreach ($part in ($Path -split '[\\/]')) {
        if ($part -in @('','.','..') -or $part -match '[. ]$' -or $part -match '[<>"|?*]' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') { return $false }
    }
    return $true
}
function Get-InstallRomRules {
    return @{
        PSP=@('PSP','iso|cso|chd|pbp'); PPSSPP=@('PSP','iso|cso|chd|pbp')
        PS=@('PS','cue|bin|chd|m3u|pbp|img|iso|ccd|sub|wav|flac|ape')
        FC=@('FC','nes|fds|unif|unf|zip|7z'); SFC=@('SFC','sfc|smc|fig|gd3|gd7|dx2|bsx|bs|swc|st|zip|7z')
        GB=@('GB','gb|gbc|bin|dmg|zip|7z'); GBC=@('GBC','gb|gbc|bin|dmg|zip|7z')
        GBA=@('GBA','gba|bin|zip|7z'); MD=@('MD','gen|smd|md|32x|bin|iso|sms|68k|chd|zip|7z')
        N64=@('N64','n64|z64|v64|zip|7z'); NDS=@('NDS','nds|zip|7z|rar|cia|dsi|srl')
    }
}
function Get-InstallRomPlan([string]$Backup) {
    Assert-NoLinks $Backup
    $statusPath=Join-Path $Backup 'backup-status.json'
    $manifestPath=Join-Path $Backup 'files-private.json'
    $payload=Join-Path $Backup 'card-files'
    Assert-NoLinks $statusPath; Assert-NoLinks $manifestPath; Assert-NoLinks $payload
    if ((Get-Item -LiteralPath $manifestPath).Length -gt 67108864) { throw 'Backup manifest too large.' }
    $status=Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
    if ($status.state -ne 'verified-file-copy') { throw 'This backup is not marked as a verified file copy.' }
    $raw=Get-Content -LiteralPath $manifestPath -Raw
    if (-not $raw.TrimStart().StartsWith('[')) { throw 'Backup manifest must be an array.' }
    $entries=@(ConvertFrom-Json -InputObject $raw)
    if ($entries.Count -ne $status.source_files -or $entries.Count -ne $status.verified_files -or $entries.Count -gt 250000) { throw 'Backup counts differ from its manifest.' }
    $rules=Get-InstallRomRules
    $known=New-Object 'System.Collections.Generic.List[object]'
    $review=New-Object 'System.Collections.Generic.List[object]'
    $seen=@{}
    foreach ($entry in $entries) {
        if (-not (Test-InstallRelativePath $entry.path) -or $entry.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $entry.bytes -lt 0) { throw 'Unsafe or malformed manifest entry.' }
        $relative=($entry.path -replace '\\','/')
        if ($seen.ContainsKey($relative)) { throw 'Duplicate or case-colliding manifest path.' };$seen[$relative]=$true
        if ($relative -notmatch '^(?i:Roms)/([^/]+)/(.+)$') { continue }
        $system=$Matches[1];$suffix=$Matches[2];$extension=[IO.Path]::GetExtension($suffix).TrimStart('.').ToLowerInvariant()
        if ($rules.ContainsKey($system) -and $extension -in ($rules[$system][1] -split '\|')) {
            $known.Add([pscustomobject]@{source=$relative;source_system=$system;system=$rules[$system][0];destination=('Roms/'+$rules[$system][0]+'/'+$suffix);bytes=[long]$entry.bytes;sha256=$entry.sha256})
        } else {
            $review.Add([pscustomobject]@{source=$relative;reason='Unknown system or non-game/unsupported extension; retained in original backup.'})
        }
    }
    return [pscustomobject]@{schema=1;backup=[IO.Path]::GetFullPath($Backup);files=$known.ToArray();review=$review.ToArray();saves_migrated=$false;device_ready=$false;note='Planning reads metadata only. Copy rechecks every selected source hash. This manifest is consistency evidence, not authenticated provenance.'}
}
function Assert-InstallDiscDependencies([string]$Payload, $Selected) {
    $byPath=@{}
    foreach ($entry in $Selected) { $byPath[[IO.Path]::GetFullPath((Join-Path $Payload $entry.source))]=$entry }
    foreach ($entry in $Selected) {
        $ext=[IO.Path]::GetExtension($entry.source).ToLowerInvariant()
        $source=Join-Path $Payload $entry.source
        if ($ext -eq '.ccd') {
            $image=[IO.Path]::ChangeExtension([IO.Path]::GetFullPath($source),'img')
            if (-not $byPath.ContainsKey($image)) { throw "CCD needs its same-name IMG companion: $($entry.source)" }
            continue
        }
        if ($ext -notin @('.cue','.m3u')) { continue }
        if ($entry.bytes -gt 8388608) { throw "Disc metadata is unexpectedly large: $($entry.source)" }
        $references=New-Object 'System.Collections.Generic.List[string]'
        foreach ($line in [IO.File]::ReadAllLines($source)) {
            $value=$line.Trim()
            if ($ext -eq '.m3u') {
                if ($value.Length -gt 0 -and -not $value.StartsWith('#')) { $references.Add($value) }
            } elseif ($value -match '^(?i:FILE)\s+(?:"([^"\r\n]+)"|(\S+))\s+\S+\s*$') {
                if ($Matches[1]) { $references.Add($Matches[1]) } else { $references.Add($Matches[2]) }
            } elseif ($value -match '^(?i:FILE)\b') { throw "Malformed CUE file reference: $($entry.source)" }
        }
        if ($references.Count -eq 0) { throw "No disc references found: $($entry.source)" }
        $systemRoot=Join-Path $Payload ('Roms/'+$entry.source_system)
        foreach ($reference in $references) {
            $relative=$reference -replace '\\','/'
            if ($relative -match '^[\\/]' -or $relative -match '[:\x00-\x1f]' -or $relative -match '[<>"|?*]') { throw "Absolute or unsafe disc reference in $($entry.source)" }
            $resolved=[IO.Path]::GetFullPath((Join-Path ([IO.Path]::GetDirectoryName($source)) $relative))
            if (-not (Test-Within $resolved $systemRoot) -or -not $byPath.ContainsKey($resolved)) {
                throw "Missing, unsupported or unselected disc companion '$reference' in $($entry.source). Original files remain in the backup."
            }
            if ($ext -eq '.m3u' -and [IO.Path]::GetExtension($resolved).ToLowerInvariant() -eq '.m3u') { throw "Nested M3U playlist needs manual review: $($entry.source)" }
        }
    }
}
function Copy-InstallRoms($Plan, [string[]]$Systems, [string]$Workspace) {
    Assert-NoLinks $Workspace
    $payload=Join-Path $Plan.backup 'card-files';Assert-NoLinks $payload
    if ((Test-Within $Workspace $Plan.backup) -or (Test-Within $Plan.backup $Workspace)) { throw 'ROM staging and backup must be separate non-overlapping trees.' }
    $selected=@($Plan.files | Where-Object { $_.system -in $Systems })
    if ($selected.Count -eq 0) { throw 'No files selected.' }
    foreach ($system in $Systems) {
        $folders=@($selected | Where-Object { $_.system -eq $system } | Select-Object -ExpandProperty source_system -Unique)
        if ($folders.Count -gt 1) { throw "Multiple old folders map to $system (for example PSP and PPSSPP). Resolve this explicitly before copying." }
    }
    $seen=@{}
    foreach ($entry in $selected) {
        if (-not (Test-InstallRelativePath $entry.source) -or -not (Test-InstallRelativePath $entry.destination)) { throw 'Unsafe ROM path.' }
        if ($seen.ContainsKey($entry.destination)) { throw 'Two selected ROM files map to the same destination.' };$seen[$entry.destination]=$true
        $source=Join-Path $payload $entry.source;Assert-NoLinks $source
        if ((Get-Item -LiteralPath $source).Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256) { throw "Backup no longer matches its manifest: $($entry.source)" }
    }
    Assert-InstallDiscDependencies $payload $selected
    $drive=New-Object IO.DriveInfo([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Workspace)))
    $bytes=0L;foreach ($entry in $selected) { $bytes += $entry.bytes }
    if ($drive.AvailableFreeSpace -lt ($bytes+1GB)) { throw 'Insufficient laptop space for selected ROMs plus 1 GiB reserve.' }
    $destination=Join-Path $Workspace 'rom-staging'
    if (Test-Path -LiteralPath $destination) { throw 'ROM staging already exists; no files will be overwritten.' }
    [void][IO.Directory]::CreateDirectory($destination)
    $statusPath=Join-Path $Workspace 'rom-copy-status.json'
    $status=[ordered]@{state='incomplete';files=0;systems=$Systems;saves_migrated=$false;device_ready=$false;error=$null}
    Write-PrivateJson $statusPath $status
    try {
        foreach ($entry in $selected) {
            $source=Join-Path $payload $entry.source
            $target=Join-Path $destination $entry.destination
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
            $file=Get-Item -LiteralPath $source -Force
            $copyEntry=[pscustomobject]@{path=$entry.source;bytes=$entry.bytes;modified_utc_ticks=$file.LastWriteTimeUtc.Ticks;attributes=[int]$file.Attributes}
            $result=Copy-VerifiedFile $source $target $copyEntry
            if ($result.sha256 -cne $entry.sha256) { throw "Source changed since manifest verification: $($entry.source)" }
            $status.files++
        }
        $status.state='selected-rom-files-verified';Write-PrivateJson $statusPath $status
        return $destination
    } catch { $status.state='failed';$status.error=$_.Exception.Message;Write-PrivateJson $statusPath $status;throw }
}
function Start-InstallPreparation {
    if ($env:OS -ne 'Windows_NT' -or $PSVersionTable.PSVersion -lt [Version]'5.1') { throw 'Use Windows PowerShell 5.1 or later.' }
    Write-Host 'Prepare our Smart Pro install files on your LAPTOP' -ForegroundColor Cyan
    Write-Host 'This does not install or boot the custom interface. Device testing is still required.'
    Write-Host 'Do not connect or select your microSD here. Keep the existing card unchanged.'
    $parent=[Environment]::GetFolderPath('MyDocuments')
    $chosen=(Read-Host "Laptop workspace parent (Enter uses $parent)").Trim().Trim('"')
    if (-not [string]::IsNullOrWhiteSpace($chosen)) { $parent=$chosen }
    Assert-InstallWorkspace $parent
    $drive=New-Object IO.DriveInfo([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($parent)))
    if ($drive.AvailableFreeSpace -lt 15GB) { throw 'Keep at least 15 GiB free for base preparation; games need additional space.' }
    $workspace=Join-Path $parent ('SmartPro-Install-'+[DateTime]::Now.ToString('yyyyMMdd-HHmmss')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
    [void][IO.Directory]::CreateDirectory($workspace)
    Write-Host "Preparing in $workspace"
    Write-PrivateJson (Join-Path $workspace 'install-status.json') ([ordered]@{state='preparing';device_ready=$false;custom_interface_activated=$false})
    $cached=(Read-Host 'Existing spruceV4.5.4.7z path (Enter downloads the pinned official archive)').Trim().Trim('"')
    $archive=Get-InstallArchive $workspace $cached
    Write-Host 'Pinned base archive verified.' -ForegroundColor Green
    $baseExtracted=$false
    $seven=Find-InstallSevenZip
    if ($null -eq $seven) {
        Write-Host '7-Zip is not installed in its standard folder. The verified archive is ready.' -ForegroundColor Yellow
        Write-Host 'Install 7-Zip from https://www.7-zip.org/ if you want extraction; no executable is downloaded automatically.'
    } else { [void](Expand-InstallBase $archive $workspace $seven);$baseExtracted=$true;Write-Host 'Pinned base extracted on laptop.' }
    $backup=(Read-Host 'Verified TrimUI backup folder for optional game staging (Enter skips for now)').Trim().Trim('"')
    if (-not [string]::IsNullOrWhiteSpace($backup)) {
        $plan=Get-InstallRomPlan $backup
        Write-PrivateJson (Join-Path $workspace 'rom-transfer-plan-private.json') $plan
        $available=@($plan.files | Select-Object -ExpandProperty system -Unique)
        Write-Host ('Available supported systems: '+($available -join ', '))
        Write-Host ('Files requiring review and left in backup: '+$plan.review.Count)
        $selection=(Read-Host 'Systems to COPY to laptop staging, comma-separated; ALL for listed systems; Enter only saves plan').Trim()
        if (-not [string]::IsNullOrWhiteSpace($selection)) {
            if ($selection -ieq 'ALL') { $systems=$available } else { $systems=@($selection.Split(',') | ForEach-Object { $_.Trim().ToUpperInvariant() }) }
            foreach ($system in $systems) { if ($system -notin $available) { throw "Unknown selection: $system" } }
            Write-Host ('Copied and verified selected ROM files: '+(Copy-InstallRoms $plan $systems $workspace))
        }
    }
    Write-PrivateJson (Join-Path $workspace 'install-status.json') ([ordered]@{state='laptop-preparation-complete';base_extracted=$baseExtracted;base_archive=(Get-InstallPin).name;archive_sha256=(Get-InstallPin).sha256;device_ready=$false;custom_interface_activated=$false;saves_migrated=$false;next='Actual card backup, firmware/runtime observations and recovery reader required before reviewing device deployment.'})
    Write-Host "`nPREPARATION COMPLETE: $workspace" -ForegroundColor Green
    Write-Host 'Do not copy this whole folder to the card. It is a prepared base and optional game staging, not an activated custom OS.'
    Write-Host 'Keep all saves/configurations in the original backup until their actual paths and compatibility are reviewed.'
}
if ($script:InstallRunInteractive) {
    try { Start-InstallPreparation; exit 0 }
    catch { Write-Host "STOPPED: $($_.Exception.Message)" -ForegroundColor Red;Write-Host 'The microSD was not changed. Incomplete laptop files are retained.';exit 1 }
}
