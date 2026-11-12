# Kernel SW actions, step by step：這個資料夾

**圖與讀圖說明在上一層**：[figures/README.md](../README.md)。那一份把 page 狀態圖與這裡的十二張照閱讀順序排在一起，每張後面附說明。這裡只記這個資料夾放了什麼、圖是怎麼生的。

## 十二張圖

| 上一層文件裡的編號 | 檔案 | 場景與步驟 |
|---|------|------|
| 圖 1 | `01-where-tables-live.png` | 全部 |
| 圖 2 | `02-fault-lock-a.png` | `fault_ro`、`fault_rw` 的 1 到 6 |
| 圖 3 | `03-fault-job.png` | `fault_ro` 的 7 到 12 |
| 圖 4 | `04-fault-lock-b.png` | `fault_ro` 的 13 到 20，`fault_rw` 多兩步 |
| 圖 5 | `05-first-touch.png` | `first_touch` |
| 圖 6A | `06a-fault-rescue.png` | `fault_rescue` 的 12 到 23 |
| 圖 6B | `06b-fault-lost.png` | `fault_lost` 的 13 到 18 |
| 圖 7 | `07-clock-scan.png` | `evict_ro` |
| 圖 8 | `08-evict-rw-lock-a.png` | `evict_rw` 的 1 到 7 |
| 圖 9 | `09-evict-rw-job.png` | `evict_rw` 的 8 到 13 |
| 圖 10 | `10-evict-rw-lock-b.png` | `evict_rw`、`evict_rw_incompressible` 的 14 到 19 |
| 圖 11 | `11-totals.png` | 全部 |

## 檔案

```
NN-<name>.png              驗收通過的圖
prompts.md                 第八版提示詞，圖上文字的唯一來源
prompts-v1.md … -v7.md     舊版。v1、v2 是總覽層級，沒有資料結構與數字
gen1/ … gen7/              每一次生成與修改，旁邊有 .prompt.txt 與 .meta.json
generation-log.jsonl       每一次 generate、edit、accept 一行
review-*.md                逐張驗收、冷讀結果
blind-review/              只給圖的冷讀報告
```

生成用 `sketchnote-gen` skill，風格 `whiteboard`，OpenAI `gpt-image-2.5-sunburst`，品質 high，1536x1024。建立日期 2026-11-12。

圖上每一個數字都抄自 [spec/kernel-step-detail-v0.md](../../spec/kernel-step-detail-v0.md)。那份文件重新產生後數字有變，提示詞與圖要跟著改。
