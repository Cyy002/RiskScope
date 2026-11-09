
## 2026-10-20 Codex M12 獨立審查（完成，未改產品）

- 49 項必要隔離測試僅執行一次：35 passed／14 failed；其中既有 M12／M11.4／ACL／Session 共 33/33 通過，新增驗收探針 2 通過／14 失敗。不是全套回歸結果。
- 未發現新 P0 越權或自動核准證據。確認 P1：數字格式繞過、百分比用途及精度錯誤、定性假事實放行、可信 7 天被拒、決策問題／限制未進回覆模型且方案固定、非工程多輪更新未採納也未明說。P2：情境錯配仍計算，以及 Signals 來源狀態不足。
- Signals 現行為專案成員公開資料；文件撤權不等於 Signal 撤權。專案隔離、撤銷成員資格、文件／歷史遮蔽控制通過，不能宣稱支援單筆機密 Signals ACL。
- 產品與既有測試雜湊前後一致；未存取正式 runtime／Token／Volume，未操作 Podman，未呼叫模型或啟動其他 Agent。磁碟 M12 GUI 紀錄為 qwen3:8b，27B 未由本輪驗證。
- 報告與可直接複驗的證據：`ai_progress/codex-review-m12/REVIEW.md`、`review_probes.py`、`observations.json`、`test-results.txt`、`results.xml`、`isolation.json`。原始探針執行後僅從 `test_review.py` 改名，避免一般 pytest 自動收集。
- 建議 Claude 下一輪依使用者授權先修可信度／來源契約及明確未採納提示，再補決策脈絡與有條件方案；不關閉 M6/M7/M7.1，不直接寫入正式 Signals，不先增加其他領域。Codex 本輪結束，不啟動後續工作。
