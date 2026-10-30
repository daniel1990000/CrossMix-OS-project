# SPDX-License-Identifier: MIT
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../Prepare-Install.ps1') -LibraryOnly
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Expect-Failure([scriptblock]$Action,[string]$Message) {
    $failed=$false;try { & $Action | Out-Null } catch { $failed=$true }
    Assert $failed $Message
}
$root=Join-Path ([IO.Path]::GetTempPath()) ('trimui-install-test-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$passed=0
try {
    $source=Join-Path $root 'source';$backupParent=Join-Path $root 'backups';$workspace=Join-Path $root 'preparation'
    foreach ($path in @($source,$backupParent,$workspace)) { [void][IO.Directory]::CreateDirectory($path) }
    foreach ($name in @('Roms/PPSSPP/Game.iso','Roms/PS/Set/Game.cue','Roms/PS/Set/Game (Track 1).bin','Roms/PS/Set/Game.m3u','Roms/PS/Set/Game.srm','Roms/UNKNOWN/Other.bin','Saves/keep.sav','Emus/PS/config.json')) {
        $p=Join-Path $source $name;[void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($p));[IO.File]::WriteAllText($p,('bytes for '+$name))
    }
    [IO.File]::WriteAllText((Join-Path $source 'Roms/PS/Set/Game.cue'), 'FILE "Game (Track 1).bin" BINARY' + "`n  TRACK 01 MODE2/2352`n")
    [IO.File]::WriteAllText((Join-Path $source 'Roms/PS/Set/Game.m3u'), "#EXTM3U`nGame.cue`n")
    $backup=Invoke-CardBackup $source $backupParent
    $before=Get-TreeSignature @(Get-CardTree $source)
    $plan=Get-InstallRomPlan $backup
    Assert ($plan.files.Count -eq 4) 'Only four supported ROM files planned'
    Assert ($plan.review.Count -eq 2) 'Save in ROM tree and unknown console require review'
    Assert (@($plan.files | Where-Object { $_.destination -eq 'Roms/PSP/Game.iso' }).Count -eq 1) 'PPSSPP maps to PSP'
    $passed++
    $missing=@($plan.files | Where-Object { $_.source -notlike '*.bin' })
    Expect-Failure { Assert-InstallDiscDependencies (Join-Path $backup 'card-files') $missing } 'Missing disc companion refused'
    $playlist=Join-Path $backup 'card-files/Roms/PS/Set/Game.m3u'
    $originalPlaylist=[IO.File]::ReadAllText($playlist)
    [IO.File]::WriteAllText($playlist, '../../../Saves/keep.sav')
    Expect-Failure { Assert-InstallDiscDependencies (Join-Path $backup 'card-files') $plan.files } 'Outside-system disc reference refused'
    [IO.File]::WriteAllText($playlist,$originalPlaylist)
    $passed++
    $ccd=[pscustomobject]@{source='Roms/PS/Disc.ccd';source_system='PS';system='PS';destination='Roms/PS/Disc.ccd';bytes=1;sha256=('0'*64)}
    Expect-Failure { Assert-InstallDiscDependencies (Join-Path $backup 'card-files') @($ccd) } 'CCD without IMG refused'
    $passed++
    $staged=Copy-InstallRoms $plan @('PSP','PS') $workspace
    Assert ((Get-Content -LiteralPath (Join-Path $workspace 'rom-copy-status.json') -Raw | ConvertFrom-Json).state -eq 'selected-rom-files-verified') 'Copy receipt'
    Assert (Test-Path -LiteralPath (Join-Path $staged 'Roms/PS/Set/Game.cue')) 'CUE preserved'
    Assert (Test-Path -LiteralPath (Join-Path $staged 'Roms/PS/Set/Game (Track 1).bin')) 'BIN preserved'
    Assert (Test-Path -LiteralPath (Join-Path $staged 'Roms/PS/Set/Game.m3u')) 'M3U preserved'
    Assert (-not (Test-Path -LiteralPath (Join-Path $staged 'Roms/PS/Set/Game.srm'))) 'Save never copied'
    Assert ((Get-TreeSignature @(Get-CardTree $source)) -ceq $before) 'Original source untouched'
    foreach ($item in $plan.files) {
        Assert ((Get-FileHash -LiteralPath (Join-Path $staged $item.destination)).Hash.ToLowerInvariant() -ceq $item.sha256) 'Staged bytes match backup'
    }
    $passed++
    Expect-Failure { Copy-InstallRoms $plan @('PSP','PS') $workspace } 'Never overwrite existing staging'
    $passed++
    $conflict=[pscustomobject]@{backup=$plan.backup;files=@($plan.files)+@([pscustomobject]@{source='Roms/PSP/Else.iso';source_system='PSP';system='PSP';destination='Roms/PSP/Else.iso';bytes=1;sha256=('0'*64)})}
    Expect-Failure { Copy-InstallRoms $conflict @('PSP') $workspace } 'PPSSPP plus PSP mapping requires review'
    $passed++
    Expect-Failure { Copy-InstallRoms $plan @('PS') (Join-Path $backup 'card-files') } 'Backup overlap refused'
    $passed++
    foreach ($path in @('../outside','Roms/PS/../../outside','/absolute','C:\outside','Roms/PS/NUL.bin','Roms/PS/a.','Roms/PS/a:b')) { Assert (-not (Test-InstallRelativePath $path)) "Unsafe path refused: $path" }
    $passed++
    $archive=Join-Path $root 'test.7z';[IO.File]::WriteAllText($archive,'archive fixture')
    $pin=[pscustomobject]@{bytes=(Get-Item $archive).Length;sha256=(Get-FileHash $archive).Hash.ToLowerInvariant()}
    [void](Assert-InstallArchive $archive $pin)
    $badPin=[pscustomobject]@{bytes=$pin.bytes;sha256=('0'*64)}
    Expect-Failure { Assert-InstallArchive $archive $badPin } 'Wrong archive hash refused'
    $badPin.bytes++
    Expect-Failure { Assert-InstallArchive $archive $badPin } 'Wrong archive size refused'
    $passed++
    $corrupt=Join-Path $backup 'card-files/Roms/PPSSPP/Game.iso';[IO.File]::AppendAllText($corrupt,'tampered')
    $fresh=Join-Path $root 'fresh';[void][IO.Directory]::CreateDirectory($fresh)
    Expect-Failure { Copy-InstallRoms $plan @('PSP') $fresh } 'Changed backup blocked before staging'
    Assert (-not (Test-Path -LiteralPath (Join-Path $fresh 'rom-staging'))) 'No output on bad input'
    $passed++
    $failedStatus=Get-Content -LiteralPath (Join-Path $backup 'backup-status.json') -Raw | ConvertFrom-Json
    $failedStatus.state='failed';Write-PrivateJson (Join-Path $backup 'backup-status.json') $failedStatus
    Expect-Failure { Get-InstallRomPlan $backup } 'Failed backup cannot supply plan'
    $passed++
    # Corruption while destination is verified must retain a failed receipt.
    function Get-FileHash {
        param([string]$LiteralPath,[string]$Algorithm)
        if ($LiteralPath -like '*rom-staging*') { [IO.File]::AppendAllText($LiteralPath,'bad readback') }
        Microsoft.PowerShell.Utility\Get-FileHash -LiteralPath $LiteralPath -Algorithm $Algorithm
    }
    Expect-Failure { Copy-InstallRoms $plan @('PS') $fresh } 'Corrupt copied file must fail'
    Remove-Item Function:\Get-FileHash
    Assert ((Get-Content -LiteralPath (Join-Path $fresh 'rom-copy-status.json') -Raw | ConvertFrom-Json).state -eq 'failed') 'Failure receipt retained'
    $passed++
    # Fresh preparation cannot use existing card-like folders.
    $cardLike=Join-Path $root 'card-like';[void][IO.Directory]::CreateDirectory((Join-Path $cardLike 'Roms'))
    Expect-Failure { Assert-InstallWorkspace $cardLike } 'Card-like workspace refused'
    $passed++
    # Windows PowerShell 5.1 defaults BOM-less text to the system code page.
    # Build Unicode names without non-ASCII script bytes (5.1 also reads scripts
    # using that default). Require explicit UTF-8 when reading our JSON files.
    $unicodeName='Pok'+[char]0x00e9+'mon-'+[char]0x65e5+[char]0x672c+'.iso'
    $unicodeSource=Join-Path $root 'unicode-source'
    $unicodeRoms=Join-Path $unicodeSource 'Roms/PSP'
    [void][IO.Directory]::CreateDirectory($unicodeRoms)
    [IO.File]::WriteAllText((Join-Path $unicodeRoms $unicodeName),'unicode game fixture')
    $unicodeBackup=Invoke-CardBackup $unicodeSource $backupParent
    function Get-Content {
        param([string]$LiteralPath,[switch]$Raw,[string]$Encoding)
        if ($Encoding -ne 'UTF8') { throw 'Backup JSON must use explicit UTF8 on Windows PowerShell 5.1.' }
        Microsoft.PowerShell.Management\Get-Content -LiteralPath $LiteralPath -Raw:$Raw -Encoding UTF8
    }
    try { $unicodePlan=Get-InstallRomPlan $unicodeBackup }
    finally { Remove-Item Function:\Get-Content }
    Assert ($unicodePlan.files.Count -eq 1) 'Unicode game planned'
    Assert ($unicodePlan.files[0].destination -ceq ('Roms/PSP/'+$unicodeName)) 'Unicode name preserved'
    $unicodeWorkspace=Join-Path $root 'unicode-preparation'
    [void][IO.Directory]::CreateDirectory($unicodeWorkspace)
    $unicodeStaged=Copy-InstallRoms $unicodePlan @('PSP') $unicodeWorkspace
    Assert ((Get-FileHash -LiteralPath (Join-Path $unicodeStaged ('Roms/PSP/'+$unicodeName))).Hash.ToLowerInvariant() -ceq $unicodePlan.files[0].sha256) 'Unicode staged file verified'
    $passed++
    Write-Host "PASS: $passed install-preparation fixture checks. No Windows/device execution established."
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
