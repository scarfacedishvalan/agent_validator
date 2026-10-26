[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [string]$VenvPath = 'C:\work\hackathon\.venv'
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendDirectory = Join-Path $projectRoot 'backend'
$python = Join-Path $VenvPath 'Scripts\python.exe'
$activation = Join-Path $VenvPath 'Scripts\Activate.ps1'
$npm = Get-Command npm.cmd -ErrorAction Stop

foreach ($requiredPath in @($python, $activation, (Join-Path $backendDirectory 'app\main.py'), (Join-Path $projectRoot 'node_modules\vite\bin\vite.js'))) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file is missing: $requiredPath. Restore the project dependencies before restarting."
    }
}

function Stop-PortListener {
    param([int]$Port)

    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -eq $Port })
    if ($listeners.Count -eq 0) {
        Write-Host "No existing listener on port $Port."
        return
    }

    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $processMap = @{}
    foreach ($process in $processes) {
        $processMap[[int]$process.ProcessId] = $process
    }
    $stopped = @{}
    foreach ($ownerId in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        if (-not $processMap.ContainsKey([int]$ownerId)) {
            continue
        }
        $rootId = [int]$ownerId
        $cursor = $processMap[$rootId]
        $visited = @{}
        # Uvicorn's reload supervisor must also stop, or it can recreate its worker.
        while ($cursor -and -not $visited.ContainsKey([int]$cursor.ProcessId)) {
            $visited[[int]$cursor.ProcessId] = $true
            if ($cursor.CommandLine -match '(?i)\buvicorn\b.*app\.main:app') {
                $rootId = [int]$cursor.ProcessId
            }
            $cursor = $processMap[[int]$cursor.ParentProcessId]
        }
        $targetIds = [System.Collections.Generic.List[int]]::new()
        $targetIds.Add($rootId)
        for ($index = 0; $index -lt $targetIds.Count; $index++) {
            foreach ($child in $processes) {
                if ([int]$child.ParentProcessId -eq $targetIds[$index] -and
                    -not $targetIds.Contains([int]$child.ProcessId)) {
                    $targetIds.Add([int]$child.ProcessId)
                }
            }
        }
        foreach ($targetId in $targetIds) {
            if ($stopped.ContainsKey($targetId) -or $targetId -eq $PID) {
                continue
            }
            $original = $processMap[$targetId]
            $current = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId" -ErrorAction Stop
            if ($null -ne $current -and $current.CreationDate -eq $original.CreationDate) {
                Write-Host "Stopping PID $targetId ($($current.Name)) for port $Port."
                Stop-Process -Id $targetId -Force -ErrorAction Stop
            }
            $stopped[$targetId] = $true
        }
    }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $remaining = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { $_.LocalPort -eq $Port })
        if ($remaining.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "Port $Port is still occupied. Inspect the listener before retrying."
}

function Start-ServiceWindow {
    param([string]$Title, [string]$Directory, [string]$ServiceCommand)

    $escapedDirectory = $Directory.Replace("'", "''")
    $escapedActivation = $activation.Replace("'", "''")
    $command = @"
`$ErrorActionPreference = 'Stop'
`$Host.UI.RawUI.WindowTitle = '$Title'
Set-Location -LiteralPath '$escapedDirectory'
. '$escapedActivation'
$ServiceCommand
if (`$LASTEXITCODE -ne 0) { throw '$Title exited with a non-zero status. See the output above.' }
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -WorkingDirectory $Directory `
        -ArgumentList @('-NoProfile', '-NoExit', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded) `
        -PassThru
}

function Wait-ServiceReady {
    param([string]$Name, [string]$Url, [System.Diagnostics.Process]$Window)

    $deadline = (Get-Date).AddSeconds(45)
    $lastFailure = 'No response yet.'
    do {
        $Window.Refresh()
        if ($Window.HasExited) {
            throw "$Name window exited before becoming ready."
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "$Name ready: $Url" -ForegroundColor Green
                return
            }
            $lastFailure = "HTTP $($response.StatusCode)"
        } catch {
            $lastFailure = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become ready within 45 seconds. Check its window. Last error: $lastFailure"
}

if (-not $PSCmdlet.ShouldProcess(
    'Listeners on ports 8000 and 5173',
    'Force-stop existing processes (including backend reload supervisor) and restart backend/frontend'
)) {
    return
}

Write-Warning 'Restarting forcibly interrupts any active batch. Its last saved checkpoint remains available.'
Stop-PortListener -Port 8000
Stop-PortListener -Port 5173

$escapedPython = $python.Replace("'", "''")
$escapedNpm = $npm.Source.Replace("'", "''")
$backendWindow = Start-ServiceWindow -Title 'Agent Validator - Backend' -Directory $backendDirectory `
    -ServiceCommand "& '$escapedPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
$frontendWindow = Start-ServiceWindow -Title 'Agent Validator - Frontend' -Directory $projectRoot `
    -ServiceCommand "& '$escapedNpm' run dev -- --host 127.0.0.1 --port 5173 --strictPort"

Wait-ServiceReady -Name 'Backend' -Url 'http://127.0.0.1:8000/api/v1/health' -Window $backendWindow
Wait-ServiceReady -Name 'Frontend' -Url 'http://127.0.0.1:5173/' -Window $frontendWindow
Write-Host 'Convergence UI: http://127.0.0.1:5173/#convergence'
Write-Host 'Both windows remain open. Close them or press Ctrl+C in each window to stop the services.'
