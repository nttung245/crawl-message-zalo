param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$apiLauncher = Join-Path $projectRoot "scripts\run_api_windows.py"
$runtimeDir = Join-Path $projectRoot "storage\runtime"
$apiLog = Join-Path $runtimeDir "api.log"
$tunnelLog = Join-Path $runtimeDir "cloudflared.log"
$statusJson = Join-Path $runtimeDir "n8n_urls.json"
$statusTxt = Join-Path $runtimeDir "n8n_urls.txt"
$startupTxt = Join-Path $runtimeDir "startup_status.txt"

function Write-Status {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Write-Host $line
    $line | Out-File -FilePath $startupTxt -Append -Encoding utf8
}

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Wait-ForApi {
    param([string]$Url, [int]$TimeoutSeconds = 60)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5
            if ($response.success -eq $true) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Wait-ForTunnelUrl {
    param([string]$LogPath, [int]$TimeoutSeconds = 90)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $pattern = 'https://[-a-z0-9]+\.trycloudflare\.com'

    while ((Get-Date) -lt $deadline) {
        if (Test-Path $LogPath) {
            $content = Get-Content -Path $LogPath -Raw -ErrorAction SilentlyContinue
            if ($content -match $pattern) {
                return $matches[0]
            }
        }
        Start-Sleep -Seconds 2
    }
    return $null
}

if (-not (Test-Path $venvPython) -or -not (Test-Path $apiLauncher)) {
    throw "Khong tim thay .venv hoac scripts\\run_api_windows.py. Hay cai dat project truoc."
}

if (-not (Test-CommandExists "cloudflared")) {
    throw "Khong tim thay cloudflared trong PATH. Hay cai Cloudflare Tunnel truoc."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Set-Content -Path $startupTxt -Value "" -Encoding utf8
if (Test-Path $apiLog) { Remove-Item -LiteralPath $apiLog -Force }
if (Test-Path $tunnelLog) { Remove-Item -LiteralPath $tunnelLog -Force }

Write-Status "Khoi dong FastAPI tren cong $Port ..."
$apiProcess = Start-Process -FilePath $venvPython `
    -ArgumentList "`"$apiLauncher`" --host $Host --port $Port" `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiLog `
    -PassThru `
    -WindowStyle Normal

$healthUrl = "http://127.0.0.1:$Port/health"
if (-not (Wait-ForApi -Url $healthUrl)) {
    throw "API khong health-check thanh cong. Kiem tra file $apiLog"
}

Write-Status "API da san sang. Tao Cloudflare Quick Tunnel ..."
$tunnelProcess = Start-Process -FilePath "cloudflared" `
    -ArgumentList "tunnel --url http://127.0.0.1:$Port --no-autoupdate" `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $tunnelLog `
    -RedirectStandardError $tunnelLog `
    -PassThru `
    -WindowStyle Normal

$tunnelUrl = Wait-ForTunnelUrl -LogPath $tunnelLog
if (-not $tunnelUrl) {
    throw "Khong lay duoc tunnel URL. Kiem tra file $tunnelLog"
}

$runtimePayload = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    local_health_url = $healthUrl
    tunnel_base_url = $tunnelUrl
    login_url = "$tunnelUrl/login"
    crawl_url = "$tunnelUrl/crawl-linkedin-group"
    health_url = "$tunnelUrl/health"
    api_log = $apiLog
    tunnel_log = $tunnelLog
    api_pid = $apiProcess.Id
    tunnel_pid = $tunnelProcess.Id
}

$runtimePayload | ConvertTo-Json -Depth 4 | Set-Content -Path $statusJson -Encoding utf8
@"
TUNNEL BASE URL:
$tunnelUrl

N8N ENDPOINTS:
- LOGIN: $tunnelUrl/login
- CRAWL: $tunnelUrl/crawl-linkedin-group
- HEALTH: $tunnelUrl/health

LOCAL FILES:
- JSON: $statusJson
- LOG API: $apiLog
- LOG TUNNEL: $tunnelLog
"@ | Set-Content -Path $statusTxt -Encoding utf8

try {
    Set-Clipboard -Value $tunnelUrl
    Write-Status "Da copy tunnel URL vao clipboard."
} catch {
    Write-Status "Khong copy duoc vao clipboard, nhung URL da duoc luu ra file."
}

Start-Process notepad.exe $statusTxt | Out-Null
Write-Status "Hoan tat. URL tunnel da san sang de gan vao n8n."
