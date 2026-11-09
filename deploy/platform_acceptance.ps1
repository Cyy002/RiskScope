# One-shot acceptance for a REAL Windows host (Podman Desktop/WSL2). Writes deploy\evidence\Windows-<arch>-<ts>.md. Never prints tokens.
$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..')
New-Item -ItemType Directory -Force deploy\evidence | Out-Null
$ts = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'); $arch = $env:PROCESSOR_ARCHITECTURE
$out = "deploy\evidence\Windows-$arch-$ts.md"
$note = if ($env:RS_HOST_NOTE) { $env:RS_HOST_NOTE } else { '<fill in: native Windows + Podman Desktop (WSL2)>' }
@("# RiskScope platform acceptance", "- date(UTC): $ts", "- host: $([System.Environment]::OSVersion.VersionString) $arch",
  "- podman: $(podman --version 2>&1)", "- podman info: $(podman info --format '{{.Host.Arch}} rootless={{.Host.Security.Rootless}} os={{.Host.OS}}' 2>&1)",
  "- model: $(if ($env:OLLAMA_MODEL) {$env:OLLAMA_MODEL} else {'qwen3:8b'})", "- host note: $note") | Set-Content $out
$verdict = 'PASS'
foreach ($a in 'build','up','smoke','demo','restart-test') {
  "### $a`n``````" | Add-Content $out
  $o = & "$PSScriptRoot\riskscope.ps1" $a 2>&1 | Out-String
  $ok = $?
  ($o -split "`n" | Where-Object { $_ -notmatch '(?i)bearer|token[=:]' } | Select-Object -Last 40) | Add-Content $out
  "``````" | Add-Content $out
  if (-not $ok) { $verdict = 'FAIL' }
  "$a -> $(if ($ok) {'ok'} else {'FAILED'})"
}
"## VERDICT: $verdict" | Tee-Object -Append $out
"evidence file: $out"
if ($verdict -ne 'PASS') { exit 1 }
