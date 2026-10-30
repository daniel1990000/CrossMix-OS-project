param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../Inspect-Recovery.ps1') -LibraryOnly
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Expect-Failure([scriptblock]$Action) { $failed=$false; try { & $Action | Out-Null } catch { $failed=$true }; Assert $failed 'Expected rejection' }
$root=Join-Path ([IO.Path]::GetTempPath()) ('trimui-recovery-test-'+[Guid]::NewGuid().ToString('N'))
$source=Join-Path $root 'source'; $reports=Join-Path $root 'reports'
[void][IO.Directory]::CreateDirectory($source); [void][IO.Directory]::CreateDirectory($reports)
$passed=0
try {
    $system=Join-Path $source 'Saves/.config/ppsspp/PSP/SYSTEM'; [void][IO.Directory]::CreateDirectory($system)
    $controls=Join-Path $system 'controls-SmartPro.ini'
    [IO.File]::WriteAllText($controls,"[ControlMapping]`nCross = `nCircle = 1-52,10-190`nPause = 10-104`nUnknown = my-secret`n")
    [IO.File]::WriteAllText((Join-Path $system 'ppsspp.ini'),"[General]`nAutoRun = True`n[SystemParam]`nButtonPreference = 1`n[Achievements]`nToken = dont-share`n[Recent]`nFileName0 = private.iso`n")
    $cm=Join-Path $source 'System/etc'; [void][IO.Directory]::CreateDirectory($cm)
    [IO.File]::WriteAllText((Join-Path $cm 'crossmix.json'),'{"RESUME AT BOOT":1,"password":"hidden-secret"}')
    $before=(Get-FileHash -LiteralPath $controls).Hash
    $run=Invoke-RecoveryInspection $source $reports
    $text=Get-Content -LiteralPath (Join-Path $run 'recovery-inspection.json') -Raw
    $j=$text|ConvertFrom-Json
    Assert ($j.findings.Count -eq 3) 'Expected selected files only'
    Assert ($text.Contains('empty-binding') -and $text.Contains('1-52,10-190')) 'Bindings summary missing'
    Assert ($text -notmatch 'my-secret|dont-share|private.iso|hidden-secret') 'Private settings leaked'
    Assert ((Get-FileHash -LiteralPath $controls).Hash -eq $before) 'Source modified'
    Assert (-not $j.repair_applied) 'Repair must remain false';$passed++
    $s=Get-RecoveryIniSummary "[ControlMapping]`nCross=1-54`nCross=10-189`nCircle=evil`n" 'controls'
    Assert ($s.selected['ControlMapping.Cross'] -eq 'duplicate-key-review-required') 'Duplicate not detected'
    Assert ($s.selected['ControlMapping.Circle'] -eq 'unrecognized-binding-format-value-withheld') 'Unsafe value emitted'
    Assert ($s.selected['ControlMapping.Pause'] -like 'not-explicitly*') 'Missing key not distinguished';$passed++
    $empty=Join-Path $root 'empty';[void][IO.Directory]::CreateDirectory($empty)
    $r=Invoke-RecoveryInspection $empty $reports
    $t=Get-Content -LiteralPath (Join-Path $r 'recovery-inspection.json') -Raw
    Assert (($t|ConvertFrom-Json).findings.Count -eq 0) 'Empty inspection invalid';$passed++
    Expect-Failure { Invoke-RecoveryInspection $source $source };$passed++
    $large=Join-Path $system 'controls.ini';[IO.File]::WriteAllBytes($large,(New-Object byte[] 262145))
    Expect-Failure { Invoke-RecoveryInspection $source $reports };Remove-Item -LiteralPath $large;$passed++
    [IO.File]::WriteAllText((Join-Path $cm 'crossmix.json'),'not-json')
    Expect-Failure { Invoke-RecoveryInspection $source $reports };Remove-Item -LiteralPath (Join-Path $cm 'crossmix.json');$passed++
    $other=Join-Path $root 'outside';[IO.File]::WriteAllText($other,'[ControlMapping]')
    New-Item -ItemType SymbolicLink -Path $large -Target $other | Out-Null
    Expect-Failure { Invoke-RecoveryInspection $source $reports };Remove-Item -LiteralPath $large;$passed++
    $version=Join-Path $source 'Emus/PSP/PPSSPP_1.17.1/.config/ppsspp/PSP/SYSTEM';[void][IO.Directory]::CreateDirectory($version)
    [IO.File]::WriteAllText((Join-Path $version 'controls.ini'),"[ControlMapping]`nCross=1-54,10-189`nCircle=1-52,10-190")
    $r=Invoke-RecoveryInspection $source $reports
    $j=Get-Content -LiteralPath (Join-Path $r 'recovery-inspection.json') -Raw|ConvertFrom-Json
    Assert (@($j.findings|Where-Object {$_.path -like 'Emus/PSP/PPSSPP_1.17.1/*'}).Count -eq 1) 'Version path missing';$passed++
    # Standalone invocation must enter the interactive branch, even though the
    # shared helper is dot-sourced in library mode. Linux rejects at its OS guard.
    if ($env:OS -ne 'Windows_NT') {
        $shell = (Get-Process -Id $PID).Path
        $script = Join-Path $PSScriptRoot '../Inspect-Recovery.ps1'
        $log = & $shell -NoProfile -File $script 2>&1 | Out-String
        Assert ($LASTEXITCODE -eq 1 -and $log.Contains('Use the interactive helper on Windows.')) 'Standalone entry point silently skipped interactive branch'
        $passed++
    }
    Write-Host "PASS: $passed recovery inspection fixture checks; actual Windows/card not tested."
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
