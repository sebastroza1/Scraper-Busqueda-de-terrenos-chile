param(
    [switch]$OAuth,
    [switch]$BackendOnly
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendUrl = "http://127.0.0.1:8765"
$PythonEngine = Join-Path $Root "python_engine"
$PythonExe = Join-Path $PythonEngine ".venv\Scripts\python.exe"
$DesktopApp = Join-Path $Root "desktop_app"
$FlutterExe = "C:\flutter\bin\flutter.bat"
$CloudflaredExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

function Test-BackendHealth {
    try {
        $health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 2
        return $health.status -eq "ok"
    } catch {
        return $false
    }
}

function Wait-BackendHealth {
    for ($i = 0; $i -lt 40; $i++) {
        if (Test-BackendHealth) {
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Backend no respondio en $BackendUrl/health"
}

function Get-SessionToken {
    try {
        $session = Invoke-RestMethod -Uri "$BackendUrl/session" -TimeoutSec 3
        return $session.token
    } catch {
        return $null
    }
}

function Show-MercadoLibreStatus {
    $token = Get-SessionToken
    if (-not $token) {
        Write-Host "Mercado Libre: REQUIERE AUTORIZACION"
        return "REQUIERE_AUTORIZACION"
    }
    try {
        $headers = @{ Authorization = "Bearer $token" }
        $diagnostic = Invoke-RestMethod `
            -Method Post `
            -Uri "$BackendUrl/credentials/diagnostics/mercadolibre_real_estate" `
            -Headers $headers `
            -TimeoutSec 12
        if ($diagnostic.status -eq "CONNECTED") {
            Write-Host "Mercado Libre: CONNECTED"
            return "CONNECTED"
        } else {
            Write-Host "Mercado Libre: REQUIERE AUTORIZACION"
            return "REQUIERE_AUTORIZACION"
        }
    } catch {
        Write-Host "Mercado Libre: REQUIERE AUTORIZACION"
        return "REQUIERE_AUTORIZACION"
    }
}

function Start-BackendIfNeeded {
    if (Test-BackendHealth) {
        Write-Host "Backend: OK $BackendUrl"
        return
    }
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "No existe Python virtualenv: $PythonExe"
    }
    $command = "Set-Location -LiteralPath '$PythonEngine'; & '$PythonExe' -m landfinder --port 8765 --data-dir ..\data"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command
    Wait-BackendHealth
    Write-Host "Backend: OK $BackendUrl"
}

function Start-CloudflareTunnel {
    if (-not (Test-Path -LiteralPath $CloudflaredExe)) {
        Write-Host "Cloudflare: no encontrado en $CloudflaredExe"
        return $null
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c `"`"$CloudflaredExe`" tunnel --url $BackendUrl 2>&1`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.CreateNoWindow = $false
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    Write-Host "Cloudflare: iniciado"

    $pattern = "https://[A-Za-z0-9-]+\.trycloudflare\.com"
    $url = $null
    $lineTask = $process.StandardOutput.ReadLineAsync()
    for ($i = 0; $i -lt 120 -and -not $url; $i++) {
        if ($lineTask.Wait(500)) {
            $line = $lineTask.Result
            if ($line) {
                Write-Host $line
                $match = [regex]::Match($line, $pattern)
                if ($match.Success) {
                    $url = $match.Value
                    break
                }
            }
            if (-not $process.HasExited) {
                $lineTask = $process.StandardOutput.ReadLineAsync()
            }
        }
    }
    if (-not $url) {
        Write-Host "Cloudflare: no pude capturar la URL automaticamente; revisa la salida de cloudflared."
        return $null
    }
    return $url
}

function Set-MercadoLibreRedirectUri {
    param([string]$TunnelUrl)

    $token = Get-SessionToken
    if (-not $token) {
        return
    }
    $redirectUri = "$TunnelUrl/oauth/mercadolibre/callback"
    $headers = @{ Authorization = "Bearer $token" }
    $body = @{ mercadolibre_redirect_uri = $redirectUri } | ConvertTo-Json
    Invoke-RestMethod `
        -Method Put `
        -Uri "$BackendUrl/settings" `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 5 | Out-Null

    Write-Host ""
    Write-Host "========================================"
    Write-Host "MERCADO LIBRE REQUIERE AUTORIZACION"
    Write-Host ""
    Write-Host "NUEVO TUNEL:"
    Write-Host $TunnelUrl
    Write-Host ""
    Write-Host "REDIRECT URI:"
    Write-Host $redirectUri
    Write-Host "========================================"
    Write-Host "1. Copia Redirect URI."
    Write-Host "2. Actualizala en Mercado Libre Developers."
    Write-Host "3. Landfinder ya utilizara esa misma Redirect URI local."
    Write-Host "4. Pulsa `"Conectar Mercado Libre`"."
}

function Test-FlutterAlreadyRunning {
    try {
        $processes = Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -like "*flutter.bat*run*-d windows*" }
        return $null -ne $processes
    } catch {
        return $false
    }
}

function Start-FlutterIfNeeded {
    if (Test-FlutterAlreadyRunning) {
        Write-Host "Flutter: ya parece estar ejecutandose"
        return
    }
    if (-not (Test-Path -LiteralPath $FlutterExe)) {
        throw "No existe Flutter: $FlutterExe"
    }
    $command = "Set-Location -LiteralPath '$DesktopApp'; & '$FlutterExe' run -d windows"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $command
    Write-Host "Flutter: iniciado"
}

Start-BackendIfNeeded
$mercadoLibreStatus = Show-MercadoLibreStatus

if ($OAuth -or $mercadoLibreStatus -ne "CONNECTED") {
    $tunnelUrl = Start-CloudflareTunnel
    if ($tunnelUrl) {
        Set-MercadoLibreRedirectUri -TunnelUrl $tunnelUrl
    }
} elseif (-not $BackendOnly) {
    Write-Host "Cloudflare: no requerido"
}

if (-not $BackendOnly) {
    Start-FlutterIfNeeded
}
