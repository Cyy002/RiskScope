# Windows PowerShell driver (Podman Desktop / podman machine on WSL2). NOT yet run on a real Windows host.
# Usage: .\deploy\riskscope.ps1 build|up|smoke|restart-test|creds|down|purge
param([Parameter(Mandatory=$true)][string]$Action)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Pod { podman @args; if ($LASTEXITCODE -ne 0) { throw "podman $($args -join ' ') failed (exit $LASTEXITCODE)" } }
function PodQuiet { podman @args 2>$null; return $LASTEXITCODE }
$Name  = if ($env:RS_NAME) { $env:RS_NAME } else { 'riskscope-portable' }
$Vol   = if ($env:RS_VOLUME) { $env:RS_VOLUME } else { 'riskscope_portable_data' }
$Port  = if ($env:RS_PORT) { $env:RS_PORT } else { '8100' }
$Image = if ($env:RS_IMAGE) { $env:RS_IMAGE } else { 'localhost/riskscope-portable:1.0' }
$Url   = if ($env:OLLAMA_URL) { $env:OLLAMA_URL } else { 'http://host.containers.internal:11434' }
$Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { 'qwen3:8b' }
$To    = if ($env:OLLAMA_REPLY_TIMEOUT_SECONDS) { $env:OLLAMA_REPLY_TIMEOUT_SECONDS } else { '120' }
if ($Name -notmatch '^riskscope-portable[a-z0-9_.-]*$') { throw 'REFUSED: container name must match riskscope-portable*' }
if ($Vol -notmatch '^riskscope_portable[a-z0-9_.-]*$') { throw 'REFUSED: volume name must match riskscope_portable*' }
if ($Image -notmatch '^localhost/riskscope-portable:[A-Za-z0-9_.-]+$') { throw 'REFUSED: image must be localhost/riskscope-portable:<tag>' }
if ($Port -notmatch '^\d+$' -or [int]$Port -lt 1024 -or [int]$Port -gt 65535 -or $Port -eq '8000') { throw 'REFUSED: port must be 1024-65535 and not 8000' }
$Label = 'io.riskscope.portable=1'
function Owned($kind, $n) {
  if ($kind -eq 'container') { if ((PodQuiet container exists $n) -ne 0) { return $true }; $v = podman container inspect $n --format '{{index .Config.Labels "io.riskscope.portable"}}' }
  else { if ((PodQuiet volume exists $n) -ne 0) { return $true }; $v = podman volume inspect $n --format '{{index .Labels "io.riskscope.portable"}}' }
  return ($v -eq '1')
}
function RequireOwned { if (-not (Owned 'container' $Name)) { throw "REFUSED: container $Name not owned by this kit" }
                        if (-not (Owned 'volume' $Vol)) { throw "REFUSED: volume $Vol not owned by this kit" } }
$SnapPy = "import hashlib,sqlite3;c=open('/app/runtime/demo_credentials.json','rb').read();db=sqlite3.connect('/app/runtime/agent.sqlite3');ids=','.join(sorted(r[0] for r in db.execute('select id from analyses')));print(hashlib.sha256(c).hexdigest(),hashlib.sha256(ids.encode()).hexdigest())"
switch ($Action) {
 'build' { if ($env:RS_PLATFORM) { Pod build --platform $env:RS_PLATFORM -t $Image -f Containerfile . } else { Pod build -t $Image -f Containerfile . } }
 'up' { RequireOwned
   if ((PodQuiet volume exists $Vol) -ne 0) { Pod volume create --label $Label $Vol | Out-Null }
   if ((PodQuiet container exists $Name) -eq 0) { Pod rm -f $Name | Out-Null }
   Pod run -d --name $Name --label $Label --restart=unless-stopped -p "127.0.0.1:${Port}:8000" --add-host=host.containers.internal:host-gateway -v "${Vol}:/app/runtime" -e "OLLAMA_URL=$Url" -e "OLLAMA_MODEL=$Model" -e "OLLAMA_REPLY_TIMEOUT_SECONDS=$To" $Image | Out-Null
   $ok = $false
   for ($i=0; $i -lt 30; $i++) { try { (Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing).Content; $ok = $true; break } catch { Start-Sleep 2 } }
   if (-not $ok) { podman logs $Name; throw 'health check failed' } }
 'demo' { RequireOwned; Pod exec $Name python scripts/demo_scenarios.py }
 'smoke' { RequireOwned; Pod exec $Name python scripts/portable_smoke.py }
 'restart-test' { RequireOwned
   Pod exec $Name python scripts/portable_smoke.py
   $before = podman exec $Name python -c $SnapPy; if ($LASTEXITCODE -ne 0) { throw 'snapshot failed' }
   Pod restart $Name | Out-Null; Start-Sleep 8
   $after = podman exec $Name python -c $SnapPy; if ($LASTEXITCODE -ne 0) { throw 'snapshot failed' }
   if ($before -ne $after) { throw 'PERSISTENCE FAIL: credentials/analysis records changed across restart' }
   'PERSISTENCE OK: credentials hash and saved analysis records identical after restart'
   Pod exec $Name python scripts/portable_smoke.py }
 'creds' { RequireOwned; Pod exec $Name cat /app/runtime/demo_credentials.json }
 'down' { RequireOwned; if ((PodQuiet container exists $Name) -eq 0) { Pod rm -f $Name } }
 'purge' { RequireOwned
   if ((PodQuiet container exists $Name) -eq 0) { Pod rm -f $Name | Out-Null }
   if ((PodQuiet volume exists $Vol) -eq 0) { Pod volume rm $Vol } }
 default { throw 'usage: riskscope.ps1 build|up|smoke|restart-test|creds|down|purge' }
}
