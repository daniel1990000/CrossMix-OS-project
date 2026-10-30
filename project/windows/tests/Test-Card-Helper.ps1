param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../TrimUI-Card-Helper.ps1') -LibraryOnly
$root = Join-Path ([IO.Path]::GetTempPath()) ('trimui-helper-test-' + [Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$passed = 0
function Assert([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Expect-Failure([scriptblock]$Action, [string]$Message) {
    $failed = $false
    try { & $Action | Out-Null } catch { $failed = $true }
    Assert $failed $Message
}
try {
    $source = Join-Path $root 'card'
    $dest = Join-Path $root 'laptop'
    [void][IO.Directory]::CreateDirectory((Join-Path $source 'Roms/PPSSPP'))
    [void][IO.Directory]::CreateDirectory((Join-Path $source 'RetroArch/.retroarch/saves'))
    [void][IO.Directory]::CreateDirectory((Join-Path $source 'empty'))
    [void][IO.Directory]::CreateDirectory($dest)
    [IO.File]::WriteAllText((Join-Path $source 'Roms/PPSSPP/game.iso'), 'GAME fixture bytes')
    [IO.File]::WriteAllText((Join-Path $source 'RetroArch/.retroarch/saves/game.srm'), 'SAVE fixture bytes')
    [IO.File]::WriteAllText((Join-Path $source '.hidden'), 'hidden fixture')
    if ($env:OS -eq 'Windows_NT') { [IO.File]::SetAttributes((Join-Path $source '.hidden'), [IO.FileAttributes]::Hidden) }
    $before = @(Get-CardTree $source)
    $summary = Get-CardSummary $before
    Assert ($summary.files -eq 3) 'Hidden/save/game files must all be counted'
    Assert ($summary.rom_folders[0].folder -eq 'PPSSPP') 'PSP source folder detected without renaming'
    Assert ($summary.possible_save_folders.Count -eq 1) 'Save directory clue'
    $passed++
    $run = Invoke-CardBackup $source $dest
    $status = Get-Content -LiteralPath (Join-Path $run 'backup-status.json') -Raw | ConvertFrom-Json
    Assert ($status.state -eq 'verified-file-copy' -and $status.verified_files -eq 3) 'Verified copy receipt'
    Assert (Test-Path -LiteralPath (Join-Path $run 'card-files/empty') -PathType Container) 'Empty directories retained'
    Assert ((Get-Content -LiteralPath (Join-Path $run 'card-files/.hidden') -Raw) -eq 'hidden fixture') 'Hidden bytes retained'
    Assert ((Get-TreeSignature $before) -ceq (Get-TreeSignature @(Get-CardTree $source))) 'Source unchanged'
    $passed++
    Expect-Failure { New-RunDirectory $source (Join-Path $source 'empty') } 'Nested output must be rejected'
    $passed++
    $entry = $before | Where-Object { $_.path -match 'game.iso$' }
    [IO.File]::AppendAllText((Join-Path $source $entry.path), ' changed')
    Expect-Failure { Copy-VerifiedFile (Join-Path $source $entry.path) (Join-Path $dest 'changed-copy') $entry } 'Source changed before copy must be rejected'
    Assert (-not (Test-Path -LiteralPath (Join-Path $dest 'changed-copy'))) 'Changed source not copied'
    $passed++
    $freshEntry = @(Get-CardTree $source) | Where-Object { $_.path -match 'game.iso$' }
    $existing = Join-Path $dest 'existing'
    [IO.File]::WriteAllText($existing, 'keep newer data')
    Expect-Failure { Copy-VerifiedFile (Join-Path $source $freshEntry.path) $existing $freshEntry } 'Existing output must not be overwritten'
    Assert ((Get-Content -LiteralPath $existing -Raw) -eq 'keep newer data') 'Existing output preserved'
    $passed++
    $link = Join-Path $source 'link'
    if ($env:OS -eq 'Windows_NT') {
        # Junctions do not require Developer Mode / symlink privilege.
        [void](New-Item -ItemType Junction -Path $link -Target $dest)
    } else { [void](New-Item -ItemType SymbolicLink -Path $link -Target $dest) }
    Expect-Failure { Get-CardTree $source } 'Reparse/link trees must be refused'
    Remove-Item -LiteralPath $link -Force
    $passed++
    # A failure after a new backup directory exists must retain a failed receipt.
    $original = ${function:Copy-VerifiedFile}
    function Copy-VerifiedFile { throw 'simulated read failure' }
    Expect-Failure { Invoke-CardBackup $source $dest } 'Read failures must stop the copy'
    ${function:Copy-VerifiedFile} = $original
    $failedRuns = @(Get-ChildItem -LiteralPath $dest -Directory | Where-Object {
        $p = Join-Path $_.FullName 'backup-status.json'
        (Test-Path -LiteralPath $p) -and ((Get-Content -LiteralPath $p -Raw | ConvertFrom-Json).state -eq 'failed')
    })
    Assert ($failedRuns.Count -eq 1) 'Interrupted copy has failed receipt'
    $passed++
    # Corrupt the destination during readback; no verified receipt may be written.
    function Get-FileHash {
        param([string]$LiteralPath, [string]$Algorithm)
        [IO.File]::AppendAllText($LiteralPath, 'corrupted destination')
        Microsoft.PowerShell.Utility\Get-FileHash -LiteralPath $LiteralPath -Algorithm $Algorithm
    }
    Expect-Failure { Invoke-CardBackup $source $dest } 'Destination corruption must fail verification'
    Remove-Item Function:\Get-FileHash
    $failedRuns = @(Get-ChildItem -LiteralPath $dest -Directory | Where-Object {
        $p = Join-Path $_.FullName 'backup-status.json'
        (Test-Path -LiteralPath $p) -and ((Get-Content -LiteralPath $p -Raw | ConvertFrom-Json).state -eq 'failed')
    })
    Assert ($failedRuns.Count -eq 2) 'Corruption failure receipt retained'
    $passed++
    $arrayFile = Join-Path $dest 'array-check.json'
    Write-PrivateJson $arrayFile @()
    Assert ((Get-Content -LiteralPath $arrayFile -Raw).Trim() -eq '[]') 'Empty array must serialize as valid JSON array'
    Write-PrivateJson $arrayFile @([pscustomobject]@{path='one';bytes=1})
    Assert ((Get-Content -LiteralPath $arrayFile -Raw).Trim().StartsWith('[')) 'Singleton array must remain JSON array'
    $passed++
    $emptySource = Join-Path $root 'empty-card'
    [void][IO.Directory]::CreateDirectory($emptySource)
    $emptyRun = Invoke-CardBackup $emptySource $dest
    $emptyStatus = Get-Content -LiteralPath (Join-Path $emptyRun 'backup-status.json') -Raw | ConvertFrom-Json
    Assert ($emptyStatus.state -eq 'verified-file-copy' -and $emptyStatus.verified_files -eq 0) 'Empty card handled explicitly'
    Assert ((Get-Content -LiteralPath (Join-Path $emptyRun 'files-private.json') -Raw).Trim() -eq '[]') 'Empty backup manifest is valid array'
    $passed++
    Write-Host "PASS: $passed functional fixture checks; physical Windows/USB not established."
} finally {
    # Only delete this test's random temporary fixture, never operator data.
    Remove-Item -LiteralPath $root -Recurse -Force
}
