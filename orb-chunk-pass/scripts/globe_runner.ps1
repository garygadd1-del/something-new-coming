#Requires -Version 5.1
<#
.SYNOPSIS
  Plan or run the AGIOS globe tile queue (trace / shade).

.DESCRIPTION
  Dry-run is the default. The script prints one planned Godot invocation per
  row and pass. It does not start Godot, write the status markdown, or write logs.

  No-Limit Local owns the live GPU queue. Pass -Execute (or --execute) only on
  that render seat, with -Godot pointing at that seat's Godot binary. The script
  does not search PATH for Godot.

  Tile ids are A01..Z26 (26 rows x 26 columns). Each Godot process renders the
  missing PNGs for one row and one pass. Outputs are PNG files named
  tile_<id>.png under <Root>\out\globe\<pass>.

  The planned argument list matches orb_chunk/globe.py argument_list:
    --path <project> --windowed --resolution <res> <scene> --
    --worker --no-auto --no-link --pass=<pass> --tiles=<ids> --outdir=<dir>

  Single-seat default is trace,shade on node selfaware. Two-seat split: run
  -Node selfaware -Passes trace here, and -Node throne -Passes shade on throne.
  Do not run shade on both seats. Node aidev does not update the status markdown.

  Recorded Fuzzy66 binary (pass it with -Godot; it is not a default):
    C:\Users\garyg\Tools\Godot_4.7.2\Godot_v4.7.2-stable_win64.exe

.PARAMETER Execute
  Start Godot. Without this switch the script only prints the plan.
  --execute is accepted as the same gate.

.PARAMETER Godot
  Full path to Godot.exe. Required with -Execute.

.PARAMETER Node
  Seat name used in logs. Examples: selfaware, throne, aidev.

.PARAMETER Passes
  Comma-separated subset of trace,shade.

.EXAMPLE
  powershell -NoProfile -File .\scripts\globe_runner.ps1

.EXAMPLE
  powershell -NoProfile -File .\scripts\globe_runner.ps1 -Execute -Godot C:\path\to\Godot.exe -Passes trace
#>
[CmdletBinding()]
param(
  [string]$Node = 'selfaware',
  [string]$Passes = 'trace,shade',
  [string]$Godot = '',
  [string]$Root = 'C:\AGIOS\Sandbox\Render_Chunks_20261022',
  [string]$Project = '',
  [string]$Scene = 'res://refrender/globe_shot.tscn',
  [Alias('MD')]
  [string]$Markdown = 'C:\AGIOS\Ara_Brain\reports\globe_render_queue_2026-10-23.md',
  [string]$PolicyPath = 'C:\AGIOS\Sandbox\RoomTemp\gpu_policy.ps1',
  [string]$TempScript = '',
  [Alias('Res')]
  [string]$Resolution = '1024x1024',
  [int]$GodotTimeoutMs = 900000,
  [switch]$Execute,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Remaining
)

$ErrorActionPreference = 'Stop'

if ($MyInvocation.InvocationName -eq '.') {
  throw 'Run scripts/globe_runner.ps1 as a script. Do not dot-source it.'
}

$extra = @()
if ($Remaining) { $extra = @($Remaining) }
$executeTokens = @('--execute', '--Execute', '--EXECUTE')
if (@($extra | Where-Object { $executeTokens -contains $_ }).Count -gt 0) {
  $Execute = $true
}
$unknown = @($extra | Where-Object { $executeTokens -notcontains $_ })
if ($unknown.Count -gt 0) {
  throw ("Unknown arguments: " + ($unknown -join ' '))
}

if ($Node -notmatch '^[A-Za-z0-9_-]+$') {
  throw "Node must be a simple name (letters, digits, underscore, hyphen). Got '$Node'."
}
if ($Resolution -notmatch '^[1-9][0-9]*x[1-9][0-9]*$') {
  throw "Resolution must look like 1024x1024. Got '$Resolution'."
}

$passList = @($Passes.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
if ($passList.Count -eq 0) { throw 'No passes given.' }
$allowedPasses = @('trace', 'shade')
$seenPasses = @{}
foreach ($passName in $passList) {
  if ($allowedPasses -notcontains $passName) {
    throw "Unknown pass '$passName'. Allowed: trace, shade."
  }
  if ($seenPasses.ContainsKey($passName)) { throw "Duplicate pass '$passName'." }
  $seenPasses[$passName] = $true
}

function Join-WinPath {
  param([string]$Base, [string]$Child)
  # String join so a dry-run off the Windows seat still prints the plan.
  # The C: drive is not mounted here, and the path cmdlet would throw.
  $left = $Base.TrimEnd('\', '/')
  $right = $Child.TrimStart('\', '/')
  return ($left + '\' + $right)
}

function Test-PathSafe {
  param([Parameter(Mandatory)][string]$LiteralPath)
  if ($script:SkipMissingDrive) { return $false }
  try {
    return [bool](Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath -ErrorAction Stop)
  } catch {
    return $false
  }
}

$script:SkipMissingDrive = $false
if ($Root -match '^[A-Za-z]:\\') {
  $driveRoot = $Root.Substring(0, 2) + '\'
  $driveOk = $false
  try {
    $driveOk = [bool](Microsoft.PowerShell.Management\Test-Path -LiteralPath $driveRoot -ErrorAction Stop)
  } catch {
    $driveOk = $false
  }
  if (-not $driveOk) { $script:SkipMissingDrive = $true }
}

if ([string]::IsNullOrWhiteSpace($Project)) {
  $Project = Join-WinPath $Root 'src\ara_body'
}
if ([string]::IsNullOrWhiteSpace($TempScript)) {
  $TempScript = Join-WinPath $Root 'tools\gputemp.ps1'
}

function Format-Arg {
  param([string]$Arg)
  if ($Arg -match '[\s"]') {
    return '"' + ($Arg -replace '"', '\"') + '"'
  }
  return $Arg
}

function Get-PlannedArgv {
  param(
    [string]$GodotBin,
    [string]$ProjectPath,
    [string]$ResolutionValue,
    [string]$ScenePath,
    [string]$PassName,
    [string[]]$Tiles,
    [string]$OutDir
  )
  $out = $OutDir -replace '\\', '/'
  $tileArg = ($Tiles -join ',')
  # Lockstep with orb_chunk/globe.py argument_list.
  return @(
    $GodotBin,
    '--path',
    $ProjectPath,
    '--windowed',
    '--resolution',
    $ResolutionValue,
    $ScenePath,
    '--',
    '--worker',
    '--no-auto',
    '--no-link',
    "--pass=$PassName",
    "--tiles=$tileArg",
    "--outdir=$out"
  )
}

function Write-DryRun {
  param(
    [string]$NodeName,
    [string[]]$PassListValue,
    [string]$RootPath,
    [string]$ProjectPath,
    [string]$ScenePath,
    [string]$ResolutionValue,
    [string]$GodotLabel,
    [string]$PolicyPathValue,
    [int]$TimeoutMs
  )
  $rows = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.ToCharArray()
  $entries = @()
  foreach ($row in $rows) {
    $rowName = [string]$row
    $ids = @(1..26 | ForEach-Object { '{0}{1:D2}' -f $rowName, $_ })
    foreach ($passName in $PassListValue) {
      $outdir = Join-WinPath (Join-WinPath (Join-WinPath $RootPath 'out') 'globe') $passName
      $todo = @($ids | Where-Object {
        -not (Test-PathSafe -LiteralPath (Join-WinPath $outdir ('tile_{0}.png' -f $_)))
      })
      $argv = @()
      if ($todo.Count -gt 0) {
        $argv = Get-PlannedArgv -GodotBin $GodotLabel -ProjectPath $ProjectPath -ResolutionValue $ResolutionValue -ScenePath $ScenePath -PassName $passName -Tiles $todo -OutDir $outdir
      }
      $entries += [pscustomobject]@{
        Row = $rowName
        Pass = $passName
        TileCount = $todo.Count
        Argv = $argv
      }
    }
  }

  $starts = @($entries | Where-Object { $_.TileCount -gt 0 })
  Write-Output 'mode: dry-run'
  Write-Output 'Godot is not started.'
  Write-Output 'godot_invoked: false'
  Write-Output 'kind: globe'
  Write-Output "node: $NodeName"
  Write-Output ("passes: " + ($PassListValue -join ','))
  Write-Output "resolution: $ResolutionValue"
  Write-Output "root: $RootPath"
  Write-Output "project: $ProjectPath"
  Write-Output "scene: $ScenePath"
  Write-Output 'tile-ids: A01-Z26'
  Write-Output ("process_starts: " + $starts.Count)
  Write-Output "timeout-ms: $TimeoutMs"
  Write-Output 'thermal-fallback: hotspot-stop=88 core-stop=80 resume-hotspot<78 cap-hours=3'
  Write-Output "policy: read on -Execute from $PolicyPathValue"
  Write-Output 'status-markdown: not written'
  Write-Output 'seat-note: single-seat default is trace,shade. Two-seat split: selfaware trace, throne shade. Do not run shade on both.'
  Write-Output 'execute-gate: -Execute -Godot <path-to-Godot.exe> on the No-Limit Local seat'
  Write-Output '---'
  foreach ($entry in $entries) {
    if ($entry.TileCount -eq 0) {
      Write-Output ("SKIP row={0} pass={1} reason=pngs-present" -f $entry.Row, $entry.Pass)
      continue
    }
    $rendered = @($entry.Argv | ForEach-Object { Format-Arg $_ }) -join ' '
    Write-Output ("row={0} pass={1} tiles={2}" -f $entry.Row, $entry.Pass, $entry.TileCount)
    Write-Output "argv: $rendered"
  }
}

$godotLabel = $Godot
if ([string]::IsNullOrWhiteSpace($godotLabel)) { $godotLabel = 'godot' }

if (-not $Execute) {
  Write-DryRun -NodeName $Node -PassListValue $passList -RootPath $Root -ProjectPath $Project -ScenePath $Scene -ResolutionValue $Resolution -GodotLabel $godotLabel -PolicyPathValue $PolicyPath -TimeoutMs $GodotTimeoutMs
  exit 0
}

# --- execute gate: Godot starts only below this line ---

if ([string]::IsNullOrWhiteSpace($Godot)) {
  throw '-Execute requires -Godot <path-to-Godot.exe>. Refusing to search PATH.'
}
if (-not (Test-PathSafe -LiteralPath $Godot)) {
  throw "Godot binary not found: $Godot"
}
if (-not (Test-PathSafe -LiteralPath $Root)) {
  throw "Sandbox root not found: $Root"
}
if (-not (Test-PathSafe -LiteralPath $Project)) {
  throw "Godot project not found: $Project"
}
$sceneRelative = ($Scene -replace '^res://', '') -replace '/', '\'
$sceneFile = Join-WinPath $Project $sceneRelative
if (-not (Test-PathSafe -LiteralPath $sceneFile)) {
  throw "Scene file not found: $sceneFile"
}

Write-Output 'mode: execute'
Write-Output 'Godot will be started. No-Limit Local render seat only.'

$logDir = Join-WinPath $Root 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$script:LogPath = Join-WinPath $logDir ("globe_{0}.log" -f $Node)
$csvPath = Join-WinPath $logDir ("globe_{0}.csv" -f $Node)
$pidPath = Join-WinPath $logDir ("globe_{0}.pid" -f $Node)
Set-Content -LiteralPath $pidPath -Value $PID

function Write-Log {
  param([string]$Message)
  $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
  Add-Content -LiteralPath $script:LogPath -Value $line
  Write-Output $line
}

function Read-GpuTemps {
  if (-not (Test-PathSafe -LiteralPath $TempScript)) {
    return ,@($null, $null)
  }
  $output = @(powershell.exe -NoProfile -ExecutionPolicy Bypass -File $TempScript)
  $core = $null
  $hot = $null
  foreach ($line in $output) {
    if ($line -match 'GPU Core = ([\d\.]+)') { $core = [double]$Matches[1] }
    if ($line -match 'Hot Spot = ([\d\.]+)') { $hot = [double]$Matches[1] }
  }
  # Unary comma keeps the pair as one array when the caller assigns it.
  return ,@($core, $hot)
}

function Set-QueueStatus {
  param(
    [string]$MarkdownPath,
    [string]$NodeName,
    [string[]]$Ids,
    [string]$Status
  )
  if ($NodeName -eq 'aidev') { return }
  if (-not (Test-PathSafe -LiteralPath $MarkdownPath)) { return }
  $lines = [System.IO.File]::ReadAllLines($MarkdownPath)
  for ($k = 0; $k -lt $lines.Length; $k++) {
    foreach ($id in $Ids) {
      $pattern = '^\| ' + [regex]::Escape($id) + ' \| '
      if ($lines[$k] -match $pattern) {
        $cells = $lines[$k].Split('|')
        # A leading pipe makes index 4 the status cell.
        if ($cells.Length -le 4) { continue }
        $cells[4] = " $Status "
        $lines[$k] = ($cells -join '|')
      }
    }
  }
  [System.IO.File]::WriteAllLines($MarkdownPath, $lines)
}

function Wait-ForeignGodot {
  param([int]$Seconds)
  while ($true) {
    $busy = @(Get-Process -Name 'Godot*' -ErrorAction SilentlyContinue | Where-Object {
      $_.MainWindowTitle -notmatch 'Project Manager'
    })
    if ($busy.Count -eq 0) { return }
    Write-Log 'other Godot job running; waiting'
    Start-Sleep -Seconds $Seconds
  }
}

function Wait-IfHot {
  $pair = Read-GpuTemps
  $attempt = 0
  while ($null -eq $pair[1] -and $attempt -lt 5 -and (Test-PathSafe -LiteralPath $TempScript)) {
    Start-Sleep -Seconds 5
    $pair = Read-GpuTemps
    $attempt++
  }
  if ($null -eq $pair[1]) {
    Write-Log 'temp unreadable after retries; proceeding'
    return
  }
  $hotHigh = $pair[1] -ge $script:HotStop
  $coreHigh = ($null -ne $pair[0]) -and ($pair[0] -ge $script:CoreStop)
  if ($hotHigh -or $coreHigh) {
    Write-Log ("PAUSE core={0} hs={1}" -f $pair[0], $pair[1])
    do {
      Start-Sleep -Seconds 30
      $pair = Read-GpuTemps
      if ($null -eq $pair[0] -and $null -eq $pair[1]) { break }
      $hotHigh = ($null -ne $pair[1]) -and ($pair[1] -ge $script:ResumeHot)
      $coreHigh = ($null -ne $pair[0]) -and ($pair[0] -ge $script:CoreStop)
    } while ($hotHigh -or $coreHigh)
    Write-Log ("RESUME core={0} hs={1}" -f $pair[0], $pair[1])
  }
}

$script:HotStop = 88.0
$script:CoreStop = 80.0
$script:CapHours = 3.0
if (Test-PathSafe -LiteralPath $PolicyPath) {
  try {
    $policyRaw = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PolicyPath | Out-String)
    $policy = $policyRaw | ConvertFrom-Json
  } catch {
    throw "gpu policy unreadable at ${PolicyPath}: $($_.Exception.Message)"
  }
  if ($null -ne $policy.hotspot_stop_C) { $script:HotStop = [double]$policy.hotspot_stop_C }
  if ($null -ne $policy.core_stop_C) { $script:CoreStop = [double]$policy.core_stop_C }
  if ($null -ne $policy.max_hours) { $script:CapHours = [double]$policy.max_hours }
}
$script:ResumeHot = $script:HotStop - 10
$runStarted = Get-Date

Write-Log ("globe runner start node={0} passes={1} res={2} gate hs>={3} core>={4} resume hs<{5} cap={6}h timeout-ms={7}" -f `
  $Node, ($passList -join ','), $Resolution, $script:HotStop, $script:CoreStop, $script:ResumeHot, $script:CapHours, $GodotTimeoutMs)

Wait-ForeignGodot -Seconds 30

$rows = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.ToCharArray()
foreach ($row in $rows) {
  $rowName = [string]$row
  $ids = @(1..26 | ForEach-Object { '{0}{1:D2}' -f $rowName, $_ })
  foreach ($passName in $passList) {
    $outdir = Join-WinPath (Join-WinPath (Join-WinPath $Root 'out') 'globe') $passName
    $todo = @($ids | Where-Object {
      -not (Test-PathSafe -LiteralPath (Join-WinPath $outdir ('tile_{0}.png' -f $_)))
    })
    if ($todo.Count -eq 0) { continue }
    if (((Get-Date) - $runStarted).TotalHours -ge $script:CapHours) {
      Write-Log 'CAP reached'
      exit 3
    }
    Wait-IfHot
    Wait-ForeignGodot -Seconds 10
    Set-QueueStatus -MarkdownPath $Markdown -NodeName $Node -Ids $todo -Status 'rendering'
    $started = Get-Date
    $pair = Read-GpuTemps
    Write-Log ("START row {0} {1} tiles={2} core={3} hs={4}" -f $rowName, $passName, $todo.Count, $pair[0], $pair[1])

    $argv = Get-PlannedArgv -GodotBin $Godot -ProjectPath $Project -ResolutionValue $Resolution -ScenePath $Scene -PassName $passName -Tiles $todo -OutDir $outdir
    # Skip argv[0] (the binary). --tiles= stays one element so the comma-separated ids are not split.
    $argList = @($argv | Select-Object -Skip 1)
    $stdoutPath = Join-WinPath $logDir ("globe_{0}_{1}_{2}.out" -f $Node, $rowName, $passName)
    $stderrPath = Join-WinPath $logDir ("globe_{0}_{1}_{2}.err" -f $Node, $rowName, $passName)
    $startParams = @{
      FilePath = $Godot
      ArgumentList = $argList
      PassThru = $true
      RedirectStandardOutput = $stdoutPath
      RedirectStandardError = $stderrPath
    }
    # -WindowStyle exists on Windows PowerShell. pwsh on Linux rejects it.
    if (-not $PSVersionTable.Platform -or $PSVersionTable.Platform -eq 'Win32NT') {
      $startParams['WindowStyle'] = 'Normal'
    }
    $proc = Start-Process @startParams
    $null = $proc.Handle
    try { $proc.PriorityClass = 'BelowNormal' } catch {}
    if (-not $proc.WaitForExit($GodotTimeoutMs)) {
      Stop-Process -Id $proc.Id -Force
      Write-Log ("TIMEOUT row {0} {1}" -f $rowName, $passName)
    }
    $wall = [int]((Get-Date) - $started).TotalSeconds
    if ($wall -lt 5) {
      Write-Log 'Godot exited instantly; aborting'
      exit 2
    }
    foreach ($tileId in $todo) {
      $png = Join-WinPath $outdir ("tile_{0}.png" -f $tileId)
      $state = 'failed'
      if (Test-PathSafe -LiteralPath $png) { $state = 'done' }
      $csvLine = '{0},{1},{2},{3},{4},{5},{6}' -f $tileId, $passName, $Node, $Resolution, $state, $started.ToString('s'), (Get-Date).ToString('s')
      Add-Content -LiteralPath $csvPath -Value $csvLine
    }
    $pair = Read-GpuTemps
    Write-Log ("END row {0} {1} wall={2}s core={3} hs={4}" -f $rowName, $passName, $wall, $pair[0], $pair[1])
  }

  $done = @()
  $bad = @()
  foreach ($tileId in $ids) {
    $complete = $true
    foreach ($passName in $passList) {
      $png = Join-WinPath (Join-WinPath (Join-WinPath (Join-WinPath $Root 'out') 'globe') $passName) ("tile_{0}.png" -f $tileId)
      if (-not (Test-PathSafe -LiteralPath $png)) { $complete = $false }
    }
    if ($complete) { $done += $tileId } else { $bad += $tileId }
  }
  if ($done.Count -gt 0) {
    Set-QueueStatus -MarkdownPath $Markdown -NodeName $Node -Ids $done -Status 'done'
  }
  if ($bad.Count -gt 0) {
    Set-QueueStatus -MarkdownPath $Markdown -NodeName $Node -Ids $bad -Status 'failed'
  }
}

Write-Log 'globe queue complete'
exit 0
