# Human review packs

**真人審查請用這兩份文件，由精簡到完整：**
1. `HUMAN_REVIEW_FOR_USER.md`（Claude A 整理）——每題一張卡片，含模型實際回答**摘要**、AI 評審
   分數/理由、判定欄。適合先快速看過一輪、抓整體印象。
2. `HUMAN_REVIEW_FULL_FOR_USER.md`（claude-b 整理）——每題完整題目、文件、rubric 預期要點、
   **模型最終回答全文**（不是摘要）、AI 評審理由、簽名/日期判定欄。真正要下結論時請以這份為準，
   因為摘要可能遺漏細節，尤其 BB01/BB16/BB23 這幾題有爭議，務必看全文。

兩份都明確標示「AI 預審，尚未經真人確認」，完成前不得在繳交文件宣稱已通過人工審查。

Cases: BB01, BB02, BB07, BB10, BB13, BB16, BB23
Each `BBxx.md` file (原始完整版, 9000+ 行): question → documents → reference → ALL arms' actual answers + judge text → checklist. Reviewer notes by claude-b (AI, preliminary, NOT independent) are in `PRELIMINARY_AI_REVIEW.md`; a human must fill the checklists. 若還有疑問，可回來查原始檔案的完整上下文（含所有歷史批次、不只 K3）。
