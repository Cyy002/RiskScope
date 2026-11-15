# RiskScope 一鍵啟動（Windows）：由 Start_RiskScope.bat 呼叫
# 流程：檢查 Podman → 檢查本機 Ollama 模型 → 建置／啟動容器 → 健康檢查 → 自動登入並顯示操作教學
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$Root  = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Name  = if ($env:RS_NAME) { $env:RS_NAME } else { 'riskscope-portable' }
$Port  = if ($env:RS_PORT) { $env:RS_PORT } else { '8100' }
$Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { 'qwen3:8b' }
$Url   = "http://127.0.0.1:$Port"

function Ok($m)    { Write-Host "  ✓ $m" -ForegroundColor Green }
function Warn($m)  { Write-Host "  ! $m" -ForegroundColor Yellow }
function Title($n, $m) { Write-Host ""; Write-Host "[$n] $m" -ForegroundColor Cyan }
function Fail($m)  { Write-Host ""; Write-Host "  ✗ $m" -ForegroundColor Red; Write-Host ""; Read-Host "按 Enter 關閉視窗" | Out-Null; exit 1 }
function Pod { & podman @args 2>$null | Out-Null; return $LASTEXITCODE }
function Ask($m) { $a = Read-Host "  $m [Y/n]"; return ($a -notmatch '^[nN]$') }
function RefreshPath { $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') }
function HasWinget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }
function PortBusy($p) { $c = New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1', [int]$p); return $true } catch { return $false } finally { $c.Close() } }
function OllamaUp { try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3 | Out-Null; return $true } catch { return $false } }
function OllamaExe { $e = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'; if (Test-Path $e) { return $e } else { return $null } }
function OllamaListensAll { $c = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue; return [bool]($c | Where-Object { $_.LocalAddress -in @('0.0.0.0','::') }) }
function RestartOllama { Get-Process -Name 'ollama app','ollama' -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2; $env:OLLAMA_HOST = '0.0.0.0'; return (StartOllama) }
function StartOllama { $e = OllamaExe; if ($e) { Start-Process -FilePath $e -WindowStyle Hidden; for ($i=0; $i -lt 30; $i++) { if (OllamaUp) { return $true }; Start-Sleep 2 } }; return (OllamaUp) }

Write-Host "=========================================="
Write-Host "  RiskScope 跨領域 AI 決策與風險分析系統"
Write-Host "=========================================="

Title "0/5" "檢查電腦資源"
$memGB = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$freeGB = [math]::Floor((Get-PSDrive ($env:SystemDrive.TrimEnd(':'))).Free / 1GB)
if ($memGB -ge 16) { Ok "記憶體 $memGB GB" } else { Warn "記憶體 $memGB GB（建議 16 GB 以上；本機模型回覆可能較慢）" }
if ($freeGB -ge 15) { Ok "可用磁碟 $freeGB GB" } else { Warn "可用磁碟 $freeGB GB（首次安裝約需 15 GB：模型 5 GB、WSL 虛擬機與映像）" }

Title "1/5" "檢查 WSL2 與 Podman"
& wsl.exe --status *> $null
if ($LASTEXITCODE -ne 0) {
  Warn "這台電腦尚未啟用 WSL2（Podman 在 Windows 上需要它）"
  if (Ask "以系統管理員身分啟用 WSL2？（完成後需重新開機，再重新執行本檔）") {
    Start-Process -FilePath wsl.exe -ArgumentList '--install','--no-distribution' -Verb RunAs -Wait
    Fail "WSL2 已安裝，請重新開機後再雙擊 Start_RiskScope.bat"
  } else { Fail "需要 WSL2 才能執行 Podman" }
}
Ok "WSL2 已啟用"
if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
  $cand = "$env:ProgramFiles\RedHat\Podman"
  if (Test-Path "$cand\podman.exe") { $env:Path = "$cand;$env:Path" }
}
if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
  Warn "這台電腦尚未安裝 Podman"
  if ((HasWinget) -and (Ask "自動下載並安裝 Podman？（約 100 MB，可能跳出系統管理員確認）")) {
    & winget install -e --id RedHat.Podman --accept-package-agreements --accept-source-agreements
    RefreshPath
    if (Test-Path "$env:ProgramFiles\RedHat\Podman\podman.exe") { $env:Path = "$env:ProgramFiles\RedHat\Podman;$env:Path" }
  }
  if (-not (Get-Command podman -ErrorAction SilentlyContinue)) { Fail "找不到 Podman，請從 https://podman-desktop.io 手動安裝後重新執行本檔" }
}
Ok ((& podman --version) -join ' ')
function VirtGuide {
  Write-Host ""
  Write-Host "  Podman 需要 Windows 的硬體虛擬化，請依序確認：" -ForegroundColor Yellow
  Write-Host "   1. 工作管理員 → 效能 → CPU，右下「虛擬化」需為「已啟用」。"
  Write-Host "      若為「已停用」：重開機進 BIOS/UEFI，開啟 Intel VT-x（Intel Virtualization Technology）或 AMD SVM。"
  Write-Host "   2. 若這台 Windows 本身是虛擬機（Parallels、VMware、VirtualBox 等），需在該軟體設定中開啟「巢狀虛擬化」。"
  Write-Host "   3. 完成後重新開機，再雙擊 Start_RiskScope.bat。"
}
function EnableVmp {
  Warn "Windows 的「虛擬機器平台」功能尚未啟用"
  if (Ask "以系統管理員身分啟用「虛擬機器平台」與 WSL？（完成後需重新開機）") {
    Start-Process -FilePath powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command','dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart; dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart'
    Fail "已送出啟用要求，請重新開機後再雙擊 Start_RiskScope.bat"
  }
  VirtGuide; Fail "需要啟用虛擬化才能執行 Podman"
}
& podman info *> $null
if ($LASTEXITCODE -ne 0) {
  # 預先檢查虛擬化：BIOS 未開啟虛擬化，或「虛擬機器平台」未啟用時，podman machine init 一定失敗
  $cs = Get-CimInstance Win32_ComputerSystem; $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
  if (-not $cs.HypervisorPresent) {
    if ($cpu.VirtualizationFirmwareEnabled -eq $false) { Warn "BIOS/UEFI 尚未開啟 CPU 虛擬化"; VirtGuide; Fail "請先開啟虛擬化" }
    EnableVmp
  }
  $machines = & podman machine list --format '{{.Name}}' 2>$null
  if (-not $machines) {
    Write-Host "  首次使用：初始化 Podman 虛擬機（約 2–5 分鐘）…"
    & podman machine init 2>&1 | Tee-Object -Variable initLog | Out-Host
    if ($LASTEXITCODE -ne 0) {
      & podman machine rm -f *> $null   # 清掉初始化失敗留下的半成品，下次可重新建立
      if (($initLog -join "`n") -match 'HYPERV_NOT_INSTALLED|虛擬化|virtualization|Virtual Machine Platform') { EnableVmp }
      Fail "podman machine init 失敗（詳見上方訊息）"
    }
  }
  Write-Host "  啟動 Podman 虛擬機…"
  & podman machine start *> $null
  & podman info *> $null
  if ($LASTEXITCODE -ne 0) {
    Warn "Podman 虛擬機無法啟動，可能是先前初始化失敗留下的損壞狀態"
    if (Ask "刪除並重新建立 Podman 虛擬機？（不影響 RiskScope 原始碼）") {
      & podman machine rm -f *> $null
      & podman machine init; if ($LASTEXITCODE -ne 0) { & podman machine rm -f *> $null; Fail "podman machine init 失敗（詳見上方訊息）" }
      & podman machine start *> $null; & podman info *> $null
    }
    if ($LASTEXITCODE -ne 0) { Fail "無法連線 Podman，請開啟 Podman Desktop 確認虛擬機狀態" }
  }
}
Ok "Podman 已就緒"

Title "2/5" "檢查本機 LLM（Ollama）"
# Windows 上容器需透過 OLLAMA_HOST=0.0.0.0 才能連到本機 Ollama；先設定好，再啟動／重啟 Ollama
$h = [Environment]::GetEnvironmentVariable('OLLAMA_HOST','User'); if (-not $h) { $h = [Environment]::GetEnvironmentVariable('OLLAMA_HOST','Machine') }
$needRestart = $false
if ($h -ne '0.0.0.0' -and $h -notlike '0.0.0.0:*') {
  [Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0','User'); $env:OLLAMA_HOST = '0.0.0.0'; $needRestart = $true
  Ok "已設定 OLLAMA_HOST=0.0.0.0（讓容器可以連到本機模型；Windows 防火牆若詢問，請允許私人網路）"
}
if (-not (OllamaExe) -and -not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Warn "這台電腦尚未安裝 Ollama（本機 LLM 服務）"
  if ((HasWinget) -and (Ask "自動下載並安裝 Ollama？（約 1 GB）")) {
    & winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    RefreshPath
  }
}
$env:OLLAMA_HOST = '0.0.0.0'
# 已在執行、但只聽 127.0.0.1（例如設定變數後沒有完全重啟）也要重啟，否則容器連不到
if ((OllamaUp) -and ($needRestart -or -not (OllamaListensAll))) {
  Write-Host "  重新啟動 Ollama，讓它接受容器連線…"
  if (-not (RestartOllama)) { Warn "Ollama 重新啟動失敗" }
}
if (-not (OllamaUp)) { Write-Host "  啟動 Ollama…"; if (-not (StartOllama)) { Warn "Ollama 未啟動" } }
if ((OllamaUp) -and -not (OllamaListensAll)) { Warn "Ollama 仍只接受本機連線（127.0.0.1），容器可能連不到；請從系統匣完全結束 Ollama 後重新開啟" }
$olBin = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $olBin) { $c = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'; if (Test-Path $c) { $olBin = $c } }
if (OllamaUp) {
  $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
  if ($tags.models.name -contains $Model) { Ok "Ollama 已啟動，模型 $Model 可用" }
  else {
    Warn "Ollama 已啟動，但尚未下載模型 $Model"
    if ($olBin -and (Ask "現在下載 $Model？（約 5 GB，依網速需數分鐘）")) {
      & $olBin pull $Model; if ($LASTEXITCODE -eq 0) { Ok "模型下載完成" } else { Warn "下載失敗，系統將改用固定模板回覆" }
    } else { Warn "略過下載，系統將改用固定模板回覆" }
  }
} else {
  Warn "偵測不到 Ollama。系統仍可運作，但回覆改用固定模板。"
  Warn "啟用本機模型：從 https://ollama.com 安裝 Ollama 後重新執行本檔。"
}

Title "3/5" "準備 RiskScope 容器"
if ((Pod container exists $Name) -ne 0 -and (PortBusy $Port)) {
  foreach ($p in ([int]$Port + 1)..([int]$Port + 20)) { if (-not (PortBusy $p)) { Warn "Port $Port 已被其他程式使用，改用 $p"; $Port = "$p"; break } }
  $env:RS_PORT = $Port; $Url = "http://127.0.0.1:$Port"
}
if ((Pod container exists $Name) -eq 0) {
  $hp = & podman container inspect $Name --format '{{range $p, $b := .HostConfig.PortBindings}}{{range $b}}{{.HostPort}}{{end}}{{end}}' 2>$null
  if ($hp) { $Port = "$hp"; $Url = "http://127.0.0.1:$Port" }
  $running = & podman container inspect $Name --format '{{.State.Running}}' 2>$null
  if ($running -eq 'true') { Ok "容器 $Name 已在執行" }
  else { if ((Pod start $Name) -ne 0) { Fail "容器啟動失敗" }; Ok "已啟動既有容器 $Name（沿用原有資料）" }
} else {
  Write-Host "  首次執行：建置映像（第一次需下載基礎映像，約數分鐘）…"
  try { & "$Root\deploy\riskscope.ps1" build } catch { Fail "建置失敗：$($_.Exception.Message)。請參考 deploy\README_PODMAN.md 的常見問題" }
  try { & "$Root\deploy\riskscope.ps1" up | Out-Null } catch { Fail "啟動失敗：$($_.Exception.Message)。請參考 deploy\README_PODMAN.md 的常見問題" }
  Ok "容器已建置並啟動"
}

Title "4/5" "健康檢查"
$healthy = $false
for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; $healthy = $true; break } catch { Start-Sleep 2 } }
if (-not $healthy) { Fail "系統沒有回應：$Url/health（可執行 podman logs $Name 查看原因）" }
Ok "系統運作正常：$Url"
& podman exec $Name python -c "import urllib.request,os;urllib.request.urlopen(os.environ.get('OLLAMA_URL','http://host.containers.internal:11434')+'/api/tags',timeout=3)" *> $null
$probe = "import urllib.request,os;urllib.request.urlopen(os.environ.get('OLLAMA_URL','http://host.containers.internal:11434')+'/api/tags',timeout=3)"
if ($LASTEXITCODE -ne 0 -and (OllamaUp)) {
  # 常見原因：Windows 防火牆擋下 WSL 虛擬網段連到主機 11434
  if (-not (Get-NetFirewallRule -DisplayName 'RiskScope Ollama (WSL)' -ErrorAction SilentlyContinue)) {
    Warn "容器連不到本機 Ollama，可能被 Windows 防火牆擋下"
    if (Ask "以系統管理員身分新增防火牆規則（只允許 WSL 內部網段 172.16.0.0/12 連到 11434）？") {
      Start-Process -FilePath powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile','-Command',"New-NetFirewallRule -DisplayName 'RiskScope Ollama (WSL)' -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 172.16.0.0/12 -Action Allow -Profile Any"
      Start-Sleep 2
      & podman exec $Name python -c $probe *> $null
    }
  }
}
if ($LASTEXITCODE -eq 0) { Ok "容器可以連到本機 Ollama" }
else {
  Warn "容器連不到本機 Ollama，回覆會改用固定模板。可手動檢查："
  Write-Host "     1. 系統匣 Ollama 圖示 → 右鍵 Quit，再從開始選單重新開啟 Ollama"
  Write-Host "     2. PowerShell 執行 netstat -ano | findstr 11434，應看到 0.0.0.0:11434"
  Write-Host "     3. 再雙擊一次 Start_RiskScope.bat"
}

Title "5/5" "登入資訊"
try { $creds = (& podman exec $Name cat /app/runtime/demo_credentials.json) -join "`n" | ConvertFrom-Json } catch { Fail "無法讀取登入 Token" }
if (-not $creds.manager) { Fail "無法讀取登入 Token" }
Write-Host "  本機測試 Token（每台電腦首次啟動時自動產生，請勿公開）："
Write-Host "    manager  管理者：可查看全部資料、核准變更、查看稽核紀錄"
Write-Host "             $($creds.manager)"
Write-Host "    engineer 工程師：可分析、提出變更，但不能核准"
Write-Host "             $($creds.engineer)"
Write-Host "    outsider 無專案權限：用於驗證存取會被拒絕"
Write-Host "             $($creds.outsider)"
Ok "瀏覽器將以 manager 身分自動登入；要切換角色，點左下角「登出／更換身分」貼上其他 Token"

Write-Host ""
Write-Host "正在開啟瀏覽器：$Url"
Start-Process "$Url/#token=$($creds.manager)"
Start-Sleep 3
try { $null = (New-Object -ComObject WScript.Shell).AppActivate($PID) } catch {}
try { $p = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId; $null = (New-Object -ComObject WScript.Shell).AppActivate([int]$p) } catch {}

Write-Host @"

==========================================
  操作教學（瀏覽器已用 manager 身分登入）
==========================================
瀏覽器已在後方開啟，請先閱讀本教學，再切換到瀏覽器照步驟操作。
輸入範例請逐字複製；本機模型每題約需 30–60 秒（無獨立顯示卡可能更久）。

【第一部分｜固定測資：對話式 Agent】
 步驟 1  左側點「對話式 Agent」，評估情境保持「馬達升級與負載」。
 步驟 2  輸入並按「送出」：
           電源24V，名目額定10A，實際可用8A，馬達11A，輔助3A，電流夠嗎？
         預期：總電流 14A、總功率 336W；超出名目額定 40%、超出實際可用 75%；
               方案 A（僅更換馬達）為 blocked；回覆下方標示「本機 LLM 轉述」。
 步驟 3  在同一個對話繼續輸入：
           只將馬達改成9A，其餘完全不變。
         預期：12A／288W，並與上一輪比較（電流 -2A、功率 -48W）。
 步驟 4  繼續輸入：
           電源額定一直是10A，實際可用一直是8A，我只修改馬達。
         預期：維持 12A，不會誤判為電源規格被修改。
 步驟 5  按「開啟新對話」，評估情境改為「供應商交期」，輸入：
           關鍵供應商交貨延遲，品質驗證尚未完成，客戶交期不能延後，也不得更換供應商。應該如何決策？
         預期：分列已知事實與未知條件，不自行捏造成本或延誤天數。

【第二部分｜人工核准流程】
 步驟 6  左側點「決策推演」，直接按「開始分析」（使用預設問題）。
         在結果最下方「人工審核／模擬操作」選 TEST-01、blocked，按「提出模擬變更申請」。
 步驟 7  左側點「人工審核」，在申請清單按「核准」（跳出確認視窗按「確定」），
         再按「執行模擬變更」並確定；狀態依序變為 approved → executed。
 步驟 8  左側點「操作稽核」，可看到申請、核准、執行的完整紀錄。

【第三部分｜權限驗證】
 步驟 9  左下角「登出／更換身分」，貼上 engineer Token 登入（右上角顯示「研發工程師 · editor」）：
         可提出變更申請，但「人工審核」不會出現核准／執行按鈕；
         「資料與證據」看不到機密文件 DOC-CONF（manager 看得到）。
 步驟 10 再登出並貼上 outsider Token：登入被拒，顯示「此帳號沒有 demo-chamber 專案存取權限」。

【第四部分｜自由測試】
 換回 manager Token，在「對話式 Agent」自由提問，例如更換數值、要求保證、
 或要求系統忽略規則直接核准，觀察系統是否守住計算結果與人工審核界線。

完整說明：README.md、ai_progress\ASSIGNMENT2\DEMO_RUNBOOK.md
停止系統：podman stop $Name
更新程式後重新建置：podman rm -f $Name，再重新執行本檔（資料保留在 volume）
"@
Read-Host "按 Enter 關閉此視窗（系統會繼續在背景執行）" | Out-Null
