# 冷讀驗收報告：gen2 00-capacity-approaches.png

- 日期：2026-11-06
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：gen2 的 00-capacity-approaches.png

**盲測限制的說明**：圖是一次整張讀進來的，所以無法真正遮住底部 Key takeaway。第 1 到 3 題是刻意只根據畫面內容回答，但不能算完全沒看到結論。

## 1. 元件與角色

### 標題區

| 物件 | 標籤 | 理解到的角色 |
|---|---|---|
| 綠色圓形徽章 | 「1」 | 看不出來。可能是系列圖的第 1 張，但畫面上沒有其他線索 |
| 標題 | One Compression Layer, Three Ways to Save Capacity | 全圖主旨：同一層 compression，三種省容量的做法 |
| 副標 | HRT ranges stay uncompressed; the options differ in address mapping and capacity handling | HRT 範圍不壓縮，三個方案差在 address mapping 與容量處理 |

### 上半部：Common path（三個方案共用的路徑）

| 物件 | 標籤 | 理解到的角色 |
|---|---|---|
| 白色方塊 | HRT clients（Display, Modem, ISP） | 發出記憶體存取的 client。HRT 全圖沒有展開，只能從成員猜是 hard real-time |
| 白色方塊 | Other clients（CPU, GPU, NPU） | 其他 client |
| 綠色大方塊 | Shared compression layer／Address range check | 所有 client 都經過的一層，依 address range 決定要不要壓縮 |
| 白色區塊與兩排等寬小方格 | Uncompressed region／Fixed mapping, no metadata lookup | 不壓縮的記憶體區，方格等寬表示固定對應 |
| 綠色區塊與一排寬度不一的格子 | Compressed region／Managed by one option below | 壓縮的記憶體區，格寬不一表示壓縮後大小不同，由下方其中一個方案管理 |
| 無框文字 | HRT still needs DRAM QoS: compression traffic also uses bandwidth | 補充提醒：HRT 雖不壓縮，仍會受 compression traffic 搶 bandwidth 影響。沒有引線，不確定是掛在哪個物件上 |

**沒有標籤的物件**：兩個 region 裡的小方格本身沒有標籤（是 page、block 還是 chunk 都沒說）。整張圖也沒有任何方塊標明「DRAM」，只能從 region 和 QoS 那行字推測這兩區就是 DRAM。

### 下半部：Option A、B、C（三欄對照，每欄五列）

| 列 | Option A: Transparent hardware overcommit | Option B: Hardware hot/cold tiering | Option C: OS-managed compressed tier |
|---|---|---|---|
| Address mapping | OSPA → metadata → 512B chunks | OSPA → CTE → Hot or cold area | PTE → Compressed NUMA node → Layer's internal mapping |
| Data grows | Use inflation room, then add a chunk（綠） | Decompress cold page to hot area on access（綠） | Read-only tier; writes move page to DRAM first（灰） |
| Physical memory full | Balloon driver reclaims pages from OS（灰） | Compress more cold pages, then OS reclaims（灰） | Stop demotion, evict aggressively（灰） |
| OS changes | Small: add balloon driver | Small: add reclaim driver | Large: tiering, faults, reclaim |
| Main cost | Possible extra metadata lookups | Migration and decompression latency | Less benefit under heavy writes |

這些列的角色都看得懂：同一組問題逐欄比較。

### 圖例與註腳

- Green cell: handled by hardware；Grey cell: handled by OS。
- OSPA: physical address seen by OS；CTE: compression translation entry。

## 2. 看不懂的線或物件

1. **上半部的箭頭顏色讓人誤會分流依據。** 深藍線從 HRT clients 進、從 HRT range 出；綠線從 Other clients 進、從 Other ranges 出。視覺上像「看 client 決定路徑」，但方塊裡寫的是「Address range check」。如果 CPU 存取 HRT range 會怎樣？圖沒有回答。
2. **所有箭頭都是單向。** 只畫了寫入方向的「compress」，讀取時的 decompress 路徑沒有出現。不確定這是刻意簡化，還是這張圖只講一個方向。
3. **深藍與綠色箭頭不在圖例內。** 圖例只定義 cell 顏色，箭頭顏色沒有說明。
4. **下半部 address mapping 的綠色小箭頭。** 綠色在圖例裡是 hardware，但 Option C 的 PTE → Compressed NUMA node 也是綠箭頭，而 PTE 應由 OS 管理。這裡的綠色究竟只是裝飾，還是有意義，看不出來。
5. **Compressed region 是綠色，但內容寫「Managed by one option below」。** 綠色若代表 hardware，Option C 卻是 OS-managed，兩者有衝突。
6. **Option C 的 mapping 鏈和另外兩欄不對齊。** A、B 從 OSPA 走到一個實體位置（chunks、area），C 從 PTE 開始，終點卻是「Layer's internal mapping」，是一個機制而非位置。讀者無法用同一把尺比較三欄。
7. **Option C「writes move page to DRAM first」。** 上半部把 Compressed region 畫成和 Uncompressed region 並列的區域，所以 compressed tier 看起來本來就在 DRAM 裡。這句話讀起來卻像 compressed tier 不在 DRAM。推測原意是「搬到未壓縮的 DRAM」，但字面上有矛盾。
8. **Option B 的 Data grows 內容答非所問。** 列名問「資料變大怎麼辦」，格子回答的是「on access 時解壓到 hot area」，兩者的關聯要自己補。
9. **「Data grows」這個列名本身有歧義。** 第一眼可能讀成資料量變多；對照「inflation room」才推得出是「寫入後壓縮率變差、壓縮後變大」。
10. **Option B 的 Physical memory full 整格灰色。** 內容是「Compress more cold pages, then OS reclaims」，前半看起來是 hardware 動作，但整格標成 OS。
11. **上下兩部分之間沒有連線。** 上半部到下半部只靠「Managed by one option below」這行字銜接，雖然看得懂，但沒有視覺連結。
12. **徽章「1」的意義不明。**
13. **QoS 提醒的掛靠對象不明。** 這行字放在 compression layer 正下方、沒有引線，也與 HRT 的 pass through 線有一段距離。

## 3. 圖說的一句話（只看畫面）

所有 client 都經過同一層 compression：HRT 的 address range 直接通過並維持固定對應，其他範圍被壓縮；而壓縮區有 A、B、C 三種互斥的管理方案，差別在 address mapping 路徑、資料變大與實體記憶體滿時誰處理、OS 要改多少，以及主要代價。

## 4. 畫面與 Key takeaway 是否一致

Key takeaway 原文：「HRT keeps a fixed mapping; the options differ in who handles data growth, and all need the OS when physical memory runs out」

**判定：一致。**

- 「HRT keeps a fixed mapping」：對應 HRT range 到 Uncompressed region 的 Fixed mapping。
- 「differ in who handles data growth」：Data grows 列為綠、綠、灰，看得出差異。不過實際分界只有 A、B（hardware）對 C（OS），「differ」不是三者各異。
- 「all need the OS when physical memory runs out」：Physical memory full 列三格全灰，這是全圖最漂亮的對應，一眼可驗證。

有兩個小落差，都不構成不一致：

- 副標說三個方案差在「address mapping and capacity handling」，takeaway 則聚焦在 data growth 與 OS，沒有提 address mapping。
- 圖中花了不少篇幅的 OS changes 與 Main cost 兩列，takeaway 完全沒有用到。畫面也沒有推薦哪個方案，這點與 takeaway 不選邊是一致的。

## 5. 困惑指數

**2 / 5。** 結構與結論幾乎一眼可讀，困惑集中在幾個局部的用詞與顏色細節，不影響抓到主旨。

## 6. 可疑的錯字或多餘文字

- 沒有發現明顯錯字，文字也都清晰可讀。
- 可疑的用詞：「writes move page to DRAM first」（Option C），見第 2 節第 7 點。
- 可能多餘：徽章「1」。
- 應補未補：HRT 沒有展開，但註腳卻解釋了 OSPA 與 CTE；這是全圖最核心的縮寫。PTE、NUMA、QoS 同樣未解釋，不過對 SoC 架構師應不成問題。

## 全部讀完後

### 顏色的意義是否一致

**大致一致，但有破口。**

- 對得上的部分：Data grows 與 Physical memory full 兩列的綠、灰都能依圖例解讀，Key takeaway 的論證也靠這個顏色成立。
- 對不上或未定義的部分：
  - Compressed region 為綠色，但 Option C 是 OS-managed。
  - Option C 的 PTE 相關箭頭也是綠色。
  - Option B 的 Physical memory full 是混合動作，卻整格灰色。
  - 白色 cell、深藍與綠色箭頭、Key takeaway 標籤的綠底，都不在圖例內。

圖例寫的是「Green cell」，嚴格說只規範 cell，所以這些不算硬錯誤，但讀者很容易把綠色的意義套到全圖。

### 能否用自己的話說出結論

可以。所有存取都走同一層 compression，看 address range 決定是否壓縮；HRT 的範圍不壓縮，換得固定 mapping，不必查 metadata。其餘範圍有三種互斥的管理方式。前兩種在資料變大時由 hardware 吸收，OS 改動小；第三種由 OS 管理，資料要寫入時得先把 page 搬出來，OS 改動大。三者在實體記憶體真的用完時都要靠 OS 回收。換句話說，沒有一種方案能完全不動 OS。

### 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 / 5 |
| 角色是否清楚 | 是 |
| 畫面與結論是否一致 | 一致 |

### 是否建議重生

**不建議重生。** 三項條件都沒有觸發：困惑指數未達 3、角色清楚、畫面與結論一致。

如果之後因其他原因要重生，可順手修正以下幾點，依影響排序：

1. Option C 的「writes move page to DRAM first」改為明確寫出未壓縮的 DRAM，消除字面矛盾。
2. 上半部箭頭的顏色不要暗示依 client 分流，或明確標出分流只看 address range。
3. 處理 Compressed region 的綠色與 Option C 為 OS-managed 的衝突。
4. 把 HRT 加進註腳。
5. 把 Option B 的 Data grows 內容寫得能直接回答「資料變大時怎麼辦」。
