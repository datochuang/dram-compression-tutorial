# DRAM compression 專案：平台前提

這裡記的是專案負責人指定的平台前提。分析、規格、模擬、圖都要照這些前提。和這裡衝突的舊內容以這裡為準，並且要指出來。

## 平台前提

| 編號 | 前提 | 指定日期 |
|---|---|---|
| P1 | **CPU MMU 沒有 hardware page table walk。** TLB miss 之後一律進 exception，由 kernel SW 查 page table 並填 TLB。也就是 software-managed TLB | 2026-11-12 |
| P2 | **multi-core、multi-thread 的 processor。每個 core 有自己的 L1 cache，所有 core 共用一個 L2 cache** | 2026-11-12 |
| P3 | **每個 core 有一個 TLB，由該 core 的所有 hardware thread 共用。** 負責人以「假設」的說法提出，還沒對過 CPU 手冊 | 2026-11-12 |
| P4 | **LZ4 HW 可以同時接受 N 個工作。N 暫定 4。** 負責人的原話是「LZ4現在可以同時接受N個工作」與「N先用4」。4 是暫定值，不是定案 | 2026-11-13 |

P4 取代先前「LZ4 HW 只有一個 engine，一次做一個 job」的假設。

### P4 目前的讀法

這一段是寫文件時採用的讀法，不是負責人指定的。負責人有不同的意思時以負責人為準。

- LZ4 HW 同一時間最多執行 N 個 job。N 是硬體的 build parameter，FW 從 `CAP.ENGINES` 讀到。模擬與文件的數字用 N 等於 4。
- job ring 與 completion ring 仍然各一個。register 與 descriptor、completion 的格式不變。
- HW 照 ring 的順序取 job，有 engine 空著才取。completion 照做完的順序寫出，不保證與取走的順序相同。
- N 個 engine 是同一套 datapath 的 N 份，彼此不共用資料狀態。
- N 個 engine 共用一個 DRAM master port，讀與寫各一個 channel。ring 的存取優先，engine 之間輪流，一次讓一個 burst。這是 `sim/ifsim` 為了能跑而採用的假設，見「還不知道的」。

## 從前提直接推出來的事

這幾條是推論，不是負責人指定的。用到的時候要說明是推論。

1. page 在 frame 裡，也就是 PRESENT，只有在 TLB hit 的時候 kernel 才不介入。TLB miss 時 kernel 的 TLB miss handler 會跑，這和有沒有壓縮層無關，是平台本來就有的成本。
2. 每一次需要解壓縮的 fault 都先是一次 TLB miss。趕出 page 時會把 PTE 設為無效並清掉 TLB，所以 fault 的次數不會超過 TLB miss 的次數。
3. page table 只有 kernel 自己讀，硬體不讀。它的格式是 kernel 可以決定的。
4. accessed 的資訊只能由 kernel 自己記，最自然的地方是 TLB miss handler。這影響控制程序文件的 D5 與 clock 的做法。
5. L2 是所有 core 共用的資源。kernel 的表與 user SW 的資料在同一個 L2 裡競爭。
6. 照 P4，completion 回來的順序不保證等於送出的順序。kernel 只能用 tag 找 job。現有的協定本來就這樣做，見介面規格的 `FW-CPL-2` 與 `FW-JOB-5`。
7. 照 P4，N 個 job 同時在 HW 裡執行。同一個 frame 或 chunk 不可以同時出現在兩個 job 裡。這由 kernel 在 `mm_lock` 之下保證，見 `FW-JOB-6`。HW 不檢查。
8. lock 保護的是共用的資料結構，不是 engine。P4 不會讓 `mm_lock` 消失。只要好幾個 kernel SW instance 寫同一個 job ring，`ring_lock` 也還在。
9. P4 改善的是排隊：一個 DECOMPRESS 不一定要等前面的 COMPRESS 做完。kernel SW 握 lock 的時間、通知與叫醒的時間都不受 P4 影響。

## 還不知道的

不要自己假設，需要時問負責人。

- CPU 的指令集與型號。
- TLB 有幾格，有沒有 ASID。
- 同一個 core 的兩個 hardware thread 同時改 TLB 時，CPU 有什麼限制。
- 現有的 TLB miss handler 一次要多久。
- 清掉其他 core 的 TLB entry 要用什麼機制。
- L1 與 L2 的大小，cache 維護指令的行為。
- N 的最後值。目前暫定 4。
- job ring 是一個，還是每個 core 或每個 engine 各一個。
- N 個 engine 怎麼接到 DRAM：共用一個 master port，還是各有各的。`sim/ifsim` 目前假設共用一個。
- N 個 engine 是否完全相同，還是有只做 DECOMPRESS 的。
- completion 的 interrupt 送到哪一個 core。
- DRAM port 上 DECOMPRESS 的 burst 要不要比 COMPRESS 的優先。負責人 2026-11-13 的指示是「decompress burst優先級先不用模擬, 但要記著」。記在硬體設計規格 12.3 的第 21 項。沒有模擬過，不要引用任何數字。

## 現有文件裡還沒照 P1 改的地方

下面這些是在 P1 指定之前寫的，假設 CPU 硬體會自己走 page table。改之前先問負責人。

- `spec/kernel-step-detail-v0.md`：`access` 與 `rerun` 兩步寫成「硬體走 page table」，成本記 0。`pte_map` 與 `tlb_inval` 的說明用的是 ARM 的指令。
- `sim/kstep/kstep.h` 的指令數是在 Apple M1 上量的，指令的選擇是 AArch64 的。
- `spec/control-procedures-v0.md` 的 D5 把「有硬體 accessed bit」列為選項之一。
- `figures/README.md` 的圖 0 說 PRESENT 的 page 是直接存取、kernel 不介入。照 P1 這只在 TLB hit 時成立。
- 2026-11-12 的口頭回答裡用 ARM 與 x86 當例子的部分：page fault 時其他 core 的行為、TLB miss 不產生 exception。

2026-11-13 照 P1 與 P3 寫的新內容，以及改過的舊內容：

- `README.md`：以 CPU MMU 為主角的入門文件，給沒有 CPU MMU 背景的讀者。LZ4 的過程只提到接上去的位置。
- `figures/cpu-mmu-basics/`：三張白板圖，嵌在 `README.md` 裡。
- CPU MMU 動畫：`addrspace/mmu_sim.js`、`addrspace/mmu_scene.js`、`addrspace/mmu3d.src.html`。十個場景。畫 2 個 core，每個 core 2 個 hardware thread、1 個 TLB、1 個 L1，兩個 core 共用 1 個 L2，kernel SW 的 `mm_lock` 畫在 page table 旁邊。TLB 畫 3 格。格數、取代方式、cache 的行為都是範例，不是平台的數字。清掉另一個 core 的 TLB、讓其他 core 做 cache clean 與 cache invalidate 都只畫結果，機制標為不知道。順序照 `sim/hostsim` 的 kernel，但由 fault 的那份 instance 自己趕 page，沒有畫 reclaimer。只填 TLB 的 handler 畫成不拿 `mm_lock`，這件事仍然沒有設計。2026-11-13 照負責人的決定放進 `docs/mmu/`，從 GitHub Pages 發佈。
- 兩種節奏動畫：`addrspace/rhythm_sim.js`、`rhythm_scene.js`、`rhythm_draw.js`、`rhythm_state.js`、`rhythm_story.js`、`rhythm3d.src.html`。白板圖 D 會動的版本，四幕。下方的表格畫 TLB、page table 與 COT、frame，標出誰讀誰寫。模型的大小與時間都是範例；L2 以 cache line 計，一個 page 算 64 行，每個 page 用到幾行可以調，2026-11-14 加上，用來表現稀疏存取時 L2 放得下的 page 多於 TLB reach；資料那一行在不在 L2 只計數，不改變 access 的時間；page 有沒有被用過由模型直接知道（D5 還沒設計）；漂移帶進來的新 page 被當成壓縮過的；chunk pool 沒有畫。2026-11-13 照負責人的決定放進 `docs/rhythm/`。
- address 動畫裡與 P1、每個 core 一個 TLB 衝突的三句話已經改掉。這個動畫仍然沒有畫 TLB 與 core。

寫 `README.md` 時發現的：`sim/hostsim/conc.py` 的 `translate` 不經過 kernel、不拿 lock 就填 TLB。單純的 TLB refill handler 要不要拿 `mm_lock`，目前沒有設計。

## 現有內容裡還沒照 P4 改的地方

2026-11-13 已經照 P4 改過的：

- 文字：介面規格、LZ4 HW 設計規格、控制程序、dependency 分析、模擬結果的說明、`spec/kernel-sw-efficiency-in-perspective.md`。
- `sim/ifsim`：model 是 N 個 engine，預設 4。`CAP.ENGINES` 的 reset 值是 4。checker 對 `HW-CPL-1` 不再檢查順序。
- `spec/sim-results-v0.md` 與 `spec/kernel-sw-dependency-v0.md` 的數字：4 個 engine 跑出來的，並且和 1 個 engine 對照。

下面這些還是一個 engine。

- `sim/hwref`：cycle 等級的 reference 一次只做一個 job。`spec/lz4-hw-design-spec-v0.md` 第 9.1 到 9.4 節的 cycle 數是單一 job 獨佔 master port 的數字。9.5 引用的 port 共用數字來自 `sim/ifsim`，不是 cycle 等級的模擬。
- `spec/kernel-sw-dependency-v0.md` 的 5.4 與 `figures/kernel-deps/three-at-once.svg`：刻意用一個 engine 說明排隊怎麼發生，文件裡有註明。
- `sim/ifsim/checkers.py` 的 `HW-MEM-1`：burst 不帶 engine 編號，一個 engine 寫進另一個 job 的範圍時 checker 分不出來。
- `docs/` 裡已經發佈的頁面、replay、lesson 動畫與 `figures/` 裡 2026-11-13 之前的圖：畫的是一個 engine。`figures/system-overview/` 是例外，那一組已經照 P4 畫成 N 個 engine，但圖上寫的是 N 還沒指定。

N 等於 4 的模擬看到的三件事，寫文件與回答時要用到：

- fault 排在 COMPRESS 後面的等待幾乎消失。reclaimer 同時送出 2 到 8 個 COMPRESS 都可以，「2 個最好」只對一個 engine 成立。
- engine 共用 DRAM port，HW 那一段最長的一次變長。等的地方從 ring 移了一部分到 port。
- 最慢的 fault 變成碰到正在被 COMPRESS 的 page 的那一種。它等的是 kernel 自己送出的 COMPRESS，engine 再多也沒用。

## `reclaim_inflight`

- 負責人 2026-11-13 的原話是「reclaim_inflight可以改」。`sim/ifsim/params.py` 的預設值同一天從 1 改成 2。2 是寫文件時照模擬選的，不是負責人指定的。
- `sim/hostsim/kernel.py` 的 `reclaim` 與控制程序的 pseudo code 仍然一次送一個 COMPRESS。改之前先問負責人，見 dependency 分析的 K3 與 K4。
- 改了之後：負載 10 倍以上，等 free frame 的 fault 少很多，20 倍以上仍然有。基準負載出現過 1 次 fault 碰到正在被 COMPRESS 的 page。數字在 `spec/sim-results-v0.md` 的 1.8。
- 一個 engine 且 `reclaim_inflight` 等於 1 時，現在的 `sim/ifsim` 與 2026-11-11 的結果逐項相同。

## 語言

文件與對話用繁體中文，專有名詞維持英文。新檔名用不帶空格的英文。
