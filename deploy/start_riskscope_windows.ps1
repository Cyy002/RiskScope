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
function Pod { & podman @args 2>$null; return $LASTEXITCODE }

Write-Host "=========================================="
Write-Host "  RiskScope 跨領域 AI 決策與風險分析系統"
Write-Host "=========================================="

Title "1/5" "檢查 Podman"
if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
  $cand = "$env:ProgramFiles\RedHat\Podman"
  if (Test-Path "$cand\podman.exe") { $env:Path = "$cand;$env:Path" }
  else { Fail "找不到 Podman，請先安裝 Podman Desktop：https://podman-desktop.io（需啟用 WSL2）" }
}
Ok ((& podman --version) -join ' ')
& podman info *> $null
if ($LASTEXITCODE -ne 0) {
  $machines = & podman machine list --format '{{.Name}}' 2>$null
  if (-not $machines) {
    Write-Host "  首次使用：初始化 Podman 虛擬機（需 WSL2，約 2–5 分鐘）…"
    & podman machine init
    if ($LASTEXITCODE -ne 0) { Fail "podman machine init 失敗；請確認已啟用 WSL2（以系統管理員執行 wsl --install 後重新開機）" }
  }
  Write-Host "  啟動 Podman 虛擬機…"
  & podman machine start *> $null
  & podman info *> $null
  if ($LASTEXITCODE -ne 0) { Fail "無法連線 Podman，請開啟 Podman Desktop 確認虛擬機狀態" }
}
Ok "Podman 已就緒"

Title "2/5" "檢查本機 LLM（Ollama）"
$ollamaOk = $false
try {
  $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
  $ollamaOk = $true
  if ($tags.models.name -contains $Model) { Ok "Ollama 已啟動，模型 $Model 可用" }
  else {
    Warn "Ollama 已啟動，但尚未下載模型 $Model"
    $ans = Read-Host "  現在下載 $Model（約 5 GB）？[y/N]"
    if ($ans -match '^[yY]$') { & ollama pull $Model; if ($LASTEXITCODE -eq 0) { Ok "模型下載完成" } else { Warn "下載失敗，系統將改用固定模板回覆" } }
    else { Warn "略過下載，系統將改用固定模板回覆" }
  }
} catch {
  Warn "偵測不到 Ollama（http://127.0.0.1:11434）。系統仍可運作，但回覆改用固定模板。"
  Warn "啟用本機模型：安裝 Ollama（https://ollama.com）後執行 ollama pull $Model，再重新執行本檔。"
}
if ($ollamaOk) {
  $h = [Environment]::GetEnvironmentVariable('OLLAMA_HOST','User'); if (-not $h) { $h = [Environment]::GetEnvironmentVariable('OLLAMA_HOST','Machine') }
  if ($h -ne '0.0.0.0' -and $h -notlike '0.0.0.0:*') {
    Warn "Windows 上容器需要 Ollama 允許外部連線（OLLAMA_HOST=0.0.0.0），目前未設定。"
    $ans = Read-Host "  幫你設定 OLLAMA_HOST=0.0.0.0（僅限目前使用者）？[Y/n]"
    if ($ans -notmatch '^[nN]$') {
      [Environment]::SetEnvironmentVariable('OLLAMA_HOST','0.0.0.0','User')
      Ok "已設定。請從右下角系統匣結束 Ollama，再重新開啟 Ollama。"
      Read-Host "  重新開啟 Ollama 後按 Enter 繼續" | Out-Null
    } else { Warn "未設定；容器可能連不到模型，回覆會改用固定模板" }
  }
}

Title "3/5" "準備 RiskScope 容器"
if ((Pod container exists $Name) -eq 0) {
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
if ($LASTEXITCODE -eq 0) { Ok "容器可以連到本機 Ollama" } else { Warn "容器連不到本機 Ollama，回覆會改用固定模板（請確認 OLLAMA_HOST=0.0.0.0 並重新開啟 Ollama）" }

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
 步驟 7  左側點「人工審核」，在申請清單按「核准」，再按「執行模擬變更」。
 步驟 8  左側點「操作稽核」，可看到申請、核准、執行的完整紀錄。

【第三部分｜權限驗證】
 步驟 9  左下角「登出／更換身分」，貼上 engineer Token 登入：
         「人工審核」不會出現核准／執行按鈕；「資料與證據」看不到機密文件 DOC-CONF。
 步驟 10 再換成 outsider Token：無法存取專案（403 拒絕）。

【第四部分｜自由測試】
 換回 manager Token，在「對話式 Agent」自由提問，例如更換數值、要求保證、
 或要求系統忽略規則直接核准，觀察系統是否守住計算結果與人工審核界線。

完整說明：README.md、ai_progress\ASSIGNMENT2\DEMO_RUNBOOK.md
停止系統：podman stop $Name
"@
Read-Host "按 Enter 關閉此視窗（系統會繼續在背景執行）" | Out-Null
