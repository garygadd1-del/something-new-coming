<#
.SYNOPSIS
  Read-only GPU health poller for AGIOS GPU_Pipes.

.DESCRIPTION
  Writes gpu_state_<machine>.json with utilization, VRAM, and temperature.
  This process does not call AMD control APIs, does not load models, and does
  not use the network.

  Thermal policy (Gary's pause rule, config, not a kill):
  when the hottest GPU-core or CPU-core reading is >= -ThermalPauseC
  (default 78), the snapshot sets reporting_paused to true and the process
  keeps running. Resume when that reading is <= -ThermalResumeC (default 75).
  Junction/hotspot is not a pause input unless -IncludeJunction is set.
  RX 7900 -> RX 79xx is only a label.

  STOP: a regular file named STOP in -OutDir ends the loop and is left in
  place. A STOP left from a previous run is renamed to STOP.<unix>.done at
  startup. The bytes are kept. This script does not delete files.

.PARAMETER Machine
  Short label used in the file name. Example: selfaware, fuzzy66.

.PARAMETER Role
  One-line role stored in the snapshot. Example: traces+spectral.

.PARAMETER OutDir
  Directory that receives gpu_state_<machine>.json.

.PARAMETER Once
  Write one snapshot and exit.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')]
  [string]$Machine,
  [Parameter(Mandatory = $true)]
  [ValidateLength(1, 80)]
  [string]$Role,
  [Parameter(Mandatory = $true)]
  [string]$OutDir,
  [ValidateRange(1, 3600)]
  [int]$Interval = 5,
  [ValidateRange(1, 120)]
  [double]$ThermalPauseC = 78,
  [ValidateRange(0, 120)]
  [double]$ThermalResumeC = 75,
  [switch]$IncludeJunction,
  [switch]$Once
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

if ($Role -notmatch '^[A-Za-z0-9][A-Za-z0-9 _+./-]{0,79}$') {
  Write-Error 'Role must be a single short line' -ErrorAction Continue
  exit 2
}
if ($ThermalResumeC -ge $ThermalPauseC) {
  Write-Error 'ThermalResumeC must be lower than ThermalPauseC' -ErrorAction Continue
  exit 2
}

function Read-Prop($Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  $prop = $Object.PSObject.Properties[$Name]
  if ($null -eq $prop) { return $null }
  return $prop.Value
}

function Get-ShortGpu([string]$Name) {
  # RX 7900 -> RX 79xx
  if (-not $Name) { return 'GPU' }
  if ($Name -match '(\d{4})') {
    return 'RX ' + $Matches[1].Substring(0, 2) + 'xx'
  }
  return 'GPU'
}

function Get-UnixNow {
  $epoch = New-Object datetime 1970, 1, 1, 0, 0, 0, ([datetimekind]::Utc)
  return [int]([datetime]::UtcNow - $epoch).TotalSeconds
}

function Resolve-OutDir([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path)
  if (Test-Path -LiteralPath $full) {
    $item = Get-Item -LiteralPath $full
    if (-not $item.PSIsContainer) { throw 'OutDir must be a directory' }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
      throw 'refusing a reparse-point OutDir'
    }
  } else {
    New-Item -ItemType Directory -Path $full -Force | Out-Null
  }
  return $full
}

function Test-Inside([string]$Root, [string]$Candidate) {
  $prefix = $Root
  if (-not $prefix.EndsWith('\')) { $prefix = $prefix + '\' }
  return $Candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Move-StaleStop([string]$Root) {
  $stop = Join-Path $Root 'STOP'
  if (-not (Test-Path -LiteralPath $stop)) { return }
  $item = Get-Item -LiteralPath $stop
  if ($item.PSIsContainer) { throw 'STOP must be a file' }
  if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw 'refusing to rename a reparse-point STOP'
  }
  $dest = Join-Path $Root ('STOP.{0}.done' -f (Get-UnixNow))
  if (Test-Path -LiteralPath $dest) {
    $dest = Join-Path $Root ('STOP.{0}.{1}.done' -f (Get-UnixNow), $PID)
  }
  Move-Item -LiteralPath $stop -Destination $dest
}

function Get-LhmTemps {
  $gpuCore = $null
  $gpuJunction = $null
  $cpuCore = $null
  $any = $false
  try {
    $sensors = @(Get-CimInstance -Namespace 'root/LibreHardwareMonitor' -ClassName 'Sensor' -ErrorAction Stop)
  } catch {
    return [pscustomobject]@{ GpuCore = $null; GpuJunction = $null; CpuCore = $null; Any = $false }
  }
  foreach ($sensor in $sensors) {
    if ((Read-Prop $sensor 'SensorType') -ne 'Temperature') { continue }
    $id = [string](Read-Prop $sensor 'Identifier')
    $name = [string](Read-Prop $sensor 'Name')
    $raw = Read-Prop $sensor 'Value'
    if ($null -eq $raw) { continue }
    $value = [double]$raw
    $blob = ($id + ' ' + $name).ToLowerInvariant()
    $isGpu = $blob.Contains('gpu')
    $isJunction = $blob.Contains('hotspot') -or $blob.Contains('hot spot') -or $blob.Contains('junction')
    $isCpu = $blob.Contains('cpu')
    $isCore = $blob.Contains('core')
    if ($isGpu) {
      $any = $true
      if ($isJunction) {
        if ($null -eq $gpuJunction -or $value -gt $gpuJunction) { $gpuJunction = $value }
      } elseif ($null -eq $gpuCore -or $value -gt $gpuCore) {
        $gpuCore = $value
      }
    }
    if ($isCpu -and $isCore) {
      $any = $true
      if ($null -eq $cpuCore -or $value -gt $cpuCore) { $cpuCore = $value }
    }
  }
  return [pscustomobject]@{ GpuCore = $gpuCore; GpuJunction = $gpuJunction; CpuCore = $cpuCore; Any = $any }
}

function Get-GpuCounters {
  $engineSet = Get-Counter '\GPU Engine(*)\Utilization Percentage'
  $memorySet = Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage'
  $engines = @()
  $memories = @()
  if ($null -ne $engineSet) { $engines = @($engineSet.CounterSamples) }
  if ($null -ne $memorySet) { $memories = @($memorySet.CounterSamples) }
  if ($engines.Count -eq 0 -or $memories.Count -eq 0) {
    throw 'GPU performance counters returned no samples'
  }
  $util3d = 0.0
  $utilCompute = 0.0
  $byPid = @{}
  foreach ($sample in $engines) {
    $instance = [string](Read-Prop $sample 'InstanceName')
    $cooked = Read-Prop $sample 'CookedValue'
    if ($null -eq $cooked) { continue }
    $value = [double]$cooked
    if ($instance -like '*engtype_3d*') { $util3d += $value }
    if ($instance -like '*engtype_compute*') { $utilCompute += $value }
    if ($value -gt 1 -and $instance -match 'pid_(\d+)') {
      $procId = [int]$Matches[1]
      if (-not $byPid.ContainsKey($procId)) { $byPid[$procId] = 0.0 }
      $byPid[$procId] = [double]$byPid[$procId] + $value
    }
  }
  $maxBytes = 0.0
  foreach ($sample in $memories) {
    $cooked = Read-Prop $sample 'CookedValue'
    if ($null -eq $cooked) { continue }
    $value = [double]$cooked
    if ($value -gt $maxBytes) { $maxBytes = $value }
  }
  $topPid = $null
  $topUse = -1.0
  foreach ($key in @($byPid.Keys)) {
    $used = [double]$byPid[$key]
    if ($used -gt $topUse) {
      $topUse = $used
      $topPid = [int]$key
    }
  }
  return [pscustomobject]@{
    Util3d = $util3d
    UtilCompute = $utilCompute
    VramBytes = $maxBytes
    TopPid = $topPid
  }
}

function Get-JobName($TopPid, [string]$Root) {
  $job = $null
  if ($null -ne $TopPid) {
    try {
      $proc = Get-Process -Id ([int]$TopPid) -ErrorAction Stop
      $job = [string](Read-Prop $proc 'ProcessName')
    } catch {
      $job = $null
    }
  }
  $lockPath = Join-Path $Root ('lock_{0}.json' -f $Machine)
  if (Test-Path -LiteralPath $lockPath) {
    try {
      $lock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
      $candidate = [string](Read-Prop $lock 'job')
      if ($candidate -and $candidate.Length -le 80 -and $candidate -notmatch '[\r\n]') {
        $job = $candidate
      }
    } catch {
      # The lock file is optional. A bad one does not change the last job name.
    }
  }
  if ($job -and $job.Length -gt 80) { return $null }
  return $job
}

function Get-PauseDecision($Temps, [bool]$CurrentlyPaused) {
  $pauseVals = @()
  if ($null -ne $Temps.GpuCore) { $pauseVals += [double]$Temps.GpuCore }
  if ($null -ne $Temps.CpuCore) { $pauseVals += [double]$Temps.CpuCore }
  if ($IncludeJunction -and $null -ne $Temps.GpuJunction) { $pauseVals += [double]$Temps.GpuJunction }
  $hottest = $null
  if ($pauseVals.Count -gt 0) {
    $hottest = ($pauseVals | Measure-Object -Maximum).Maximum
  }
  $paused = $CurrentlyPaused
  $reason = $null
  # Pause when hottest core reading -ge ThermalPauseC.
  # Resume when hottest core reading -le ThermalResumeC.
  if ($CurrentlyPaused) {
    if ($null -ne $hottest -and $hottest -le $ThermalResumeC) {
      $paused = $false
    } else {
      $paused = $true
      if ($null -eq $hottest) {
        $reason = 'temperature sensor unavailable; reporting stays paused; process left running'
      } else {
        $reason = 'core temperature still above resume; reporting paused; process left running'
      }
    }
  } elseif ($null -ne $hottest -and $hottest -ge $ThermalPauseC) {
    $paused = $true
    $reason = "core temperature $hottest C >= pause $ThermalPauseC C; reporting paused; process left running"
  }
  return [pscustomobject]@{ Paused = $paused; Reason = $reason; Hottest = $hottest }
}

function Write-AtomicJson([string]$Root, [string]$FileName, $Object) {
  if ($FileName -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$') {
    throw 'unsafe output name'
  }
  $dest = [System.IO.Path]::GetFullPath((Join-Path $Root $FileName))
  if (-not (Test-Inside $Root $dest)) { throw 'output path escapes OutDir' }
  if (Test-Path -LiteralPath $dest) {
    $existing = Get-Item -LiteralPath $dest
    if ($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
      throw 'refusing to replace a reparse point'
    }
  }
  $tmp = $dest + '.tmp'
  if ((Test-Path -LiteralPath $tmp) -and ((Get-Item -LiteralPath $tmp).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw 'refusing to write through a reparse point'
  }
  $json = ($Object | ConvertTo-Json -Compress -Depth 4) + "`n"
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($tmp, $json, $utf8)
  Move-Item -LiteralPath $tmp -Destination $dest -Force
}

function New-Snapshot($Counters, $Temps, $Decision, [string]$GpuLabel, $JobName) {
  $display = $Temps.GpuCore
  if ($null -eq $display) { $display = $Temps.GpuJunction }
  $tempSource = 'unavailable'
  if ($Temps.Any) { $tempSource = 'LibreHardwareMonitor' }
  $util = [math]::Round([math]::Min(100, [math]::Max($Counters.Util3d, [math]::Max($Counters.UtilCompute, 0))), 1)
  $bytes = [math]::Max(0, [double]$Counters.VramBytes)
  return [ordered]@{
    schema = 'gpu_state/1'
    machine = $Machine
    gpu = $GpuLabel
    role = $Role
    util_pct = $util
    vram_used_gb = [math]::Round($bytes / 1GB, 1)
    vram_used_mb = [int][math]::Round($bytes / 1MB, 0)
    temp_c = $display
    core_temp_c = $Decision.Hottest
    temp_source = $tempSource
    reporting_paused = [bool]$Decision.Paused
    pause_reason = $Decision.Reason
    thermal_pause_c = $ThermalPauseC
    thermal_resume_c = $ThermalResumeC
    job = $JobName
    ts = (Get-Date).ToString('o')
    source = 'win-perfcounters'
  }
}

$root = Resolve-OutDir $OutDir
Move-StaleStop $root
$outName = 'gpu_state_{0}.json' -f $Machine
$script:Paused = $false
$gpuName = $null
try {
  $controllers = @(Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop)
  foreach ($controller in $controllers) {
    $name = [string](Read-Prop $controller 'Name')
    if ($name -like '*Radeon*') { $gpuName = $name; break }
  }
} catch {
  $gpuName = $null
}
$gpuLabel = Get-ShortGpu $gpuName

while ($true) {
  $stop = Join-Path $root 'STOP'
  if (Test-Path -LiteralPath $stop) { break }
  try {
    $counters = Get-GpuCounters
    $temps = Get-LhmTemps
    $decision = Get-PauseDecision $temps $script:Paused
    $script:Paused = [bool]$decision.Paused
    $job = Get-JobName $counters.TopPid $root
    $snapshot = New-Snapshot $counters $temps $decision $gpuLabel $job
    Write-AtomicJson $root $outName $snapshot
  } catch {
    Write-Warning $_.Exception.Message
    if ($Once) { exit 1 }
  }
  if ($Once) { break }
  Start-Sleep -Seconds $Interval
}
exit 0
