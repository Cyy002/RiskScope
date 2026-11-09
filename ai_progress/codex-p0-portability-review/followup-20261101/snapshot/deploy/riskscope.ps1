# Windows PowerShell driver (Podman Desktop / podman machine on WSL2). Usage: .\deploy\riskscope.ps1 build|up|smoke|restart-test|creds|down|purge
param([Parameter(Mandatory=$true)][string]$Action)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Name = if ($env:RS_NAME) { $env:RS_NAME } else { 'riskscope-portable' }
$Vol  = if ($env:RS_VOLUME) { $env:RS_VOLUME } else { 'riskscope_portable_data' }
$Port = if ($env:RS_PORT) { $env:RS_PORT } else { '8100' }
if ($Name -eq 'riskscope' -or $Vol -eq 'riskscope_runtime' -or $Port -eq '8000') { throw 'refusing reserved production name/port' }
$Image = if ($env:RS_IMAGE) { $env:RS_IMAGE } else { 'localhost/riskscope-portable:1.0' }
$Url = if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { 'http://host.containers.internal:11434' }
$Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { 'qwen3:8b' }
$To = if ($env:OLLAMA_REPLY_TIMEOUT_SECONDS) { $env:OLLAMA_REPLY_TIMEOUT_SECONDS } else { '120' }
switch ($Action) {
 'build' { podman build -t $Image -f Containerfile . }
 'up' {
   podman volume exists $Vol; if ($LASTEXITCODE -ne 0) { podman volume create $Vol | Out-Null }
   podman rm -f $Name 2>$null | Out-Null
   podman run -d --name $Name --restart=unless-stopped -p "127.0.0.1:${Port}:8000" --add-host=host.containers.internal:host-gateway -v "${Vol}:/app/runtime" `
     -e "OLLAMA_URL=$Url" -e "OLLAMA_MODEL=$Model" -e "OLLAMA_REPLY_TIMEOUT_SECONDS=$To" $Image
   $ok=$false; for ($i=0; $i -lt 30; $i++) { try { (Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing).Content; $ok=$true; break } catch { Start-Sleep 2 } }
   if (-not $ok) { podman logs $Name; throw 'health check failed' } }
 'smoke' { podman exec $Name python scripts/portable_smoke.py }
 'restart-test' { $before = podman exec $Name python -c "import json;print(json.load(open('/app/runtime/demo_credentials.json'))['engineer'])"
   podman restart $Name | Out-Null; Start-Sleep 8
   $after = podman exec $Name python -c "import json;print(json.load(open('/app/runtime/demo_credentials.json'))['engineer'])"
   if ($before -eq $after) { 'PERSISTENCE OK: credentials/db survived restart' } else { throw 'PERSISTENCE FAIL' }
   podman exec $Name python scripts/portable_smoke.py }
 'creds' { podman exec $Name cat /app/runtime/demo_credentials.json }
 'down' { podman rm -f $Name }
 'purge' { podman rm -f $Name; podman volume rm $Vol }
}
