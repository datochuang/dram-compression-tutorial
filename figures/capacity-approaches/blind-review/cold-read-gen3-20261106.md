# 冷讀驗收報告：gen3 01-how-space-is-saved.r2.png

- 日期：2026-11-06
- 方法：只給圖、不給提示詞的冷讀
- 讀的是：gen3 的 01-how-space-is-saved.r2.png

讀者設定：第一次學 DRAM compression 的工程師，懂一點電腦架構，沒接觸過記憶體壓縮。

作答限制的說明：

- 圖是一次讀入的，底部 Key takeaway 無法真的遮住。第 1 到 4 題只依上方內容作答，但不能保證完全沒受影響。
- 報告裡的寬度比例都是目測，沒有量測工具，只能當粗估。

## 1. 元件與角色

### 標題區

| 元件 | 標籤 | 表達什麼 |
|---|---|---|
| 綠色圓形徽章 | 2 | 看起來是系列圖的編號，但檔名是 01，看不出對應關係 |
| 標題 | Where the Saved Space Comes From | 這張圖要回答的問題 |
| 副標 | A smaller page leaves DRAM free, and that free DRAM can hold more pages | 整張圖的因果鏈，已經接近答案 |

### Basic idea 區

由左到右是一條因果鏈：

| 元件 | 標籤 | 表達什麼 |
|---|---|---|
| 白色實線方塊 | 4KB page | 壓縮前的一頁 |
| 綠色箭頭 | Compress | 壓縮這個動作 |
| 綠色方塊 | 2KB stored | 壓縮後實際佔用的部分 |
| 虛線方塊 | 2KB free | 省下來的部分 |
| 白色方塊 | Free DRAM stores more pages | 省下的空間拿來放更多頁 |
| 白色方塊 | OS sees more memory than is installed | 最終效果 |
| 灰字註解 | Example ratio 2:1. Worse compression leaves less free space. | 2KB 只是舉例，省多少取決於壓縮率 |

### 三個做法區

三欄都是相同的四列，可以直接橫向比較：

| 列 | Option A: Transparent hardware overcommit | Option B: Hardware hot/cold tiering | Option C: OS-managed compressed tier |
|---|---|---|---|
| Before | 4 個 Page，全白 | Hot、Hot、Cold、Cold，全白 | 同 B |
| After | 4 個變窄的綠色 Page，加一大塊 Free | 白色 Hot × 2、綠色 Cold × 2、Free | 粗黑線隔開：Normal DRAM（白色 Hot × 2）、Compressed tier（綠色 Cold × 2、Free） |
| Who picks | Hardware: every page（綠底） | Hardware: cold pages only（綠底） | OS: cold pages only（灰底） |
| OS sees | More pages than installed DRAM | More pages than installed DRAM | Extra capacity in a NUMA node |

角色大致都看得出來。不夠明確的有兩處：

- **Who picks**：列名本身沒說「挑什麼」，要看格內文字才知道是「挑哪些頁去壓縮」。A 的 every page 其實沒有在挑。
- **OS sees**：沒有直接說「空出來的空間誰能用」，只能從 OS 看到什麼去推。

### 底部

| 元件 | 標籤 | 表達什麼 |
|---|---|---|
| 圖例 | Uncompressed page（白）、Compressed page（綠）、Free DRAM（虛線） | 頁面的三種狀態 |
| 灰字註解 | HRT range not shown: its pages stay full size | 有個叫 HRT 的範圍沒畫，裡面的頁不壓縮。HRT 全圖沒有定義，**角色看不出來**，也看不出它屬於哪個做法 |

## 2. 看不懂的線或物件

1. **HRT**：不知道是什麼，也不知道適用 A、B、C 哪個。這是全圖唯一完全看不懂的東西。
2. **Option C 的粗黑線**：看得出是分界，但不確定是實體分開（不同 DRAM）還是同一塊 DRAM 的邏輯分區。A、B 沒有這條線，所以 B 的 hot 和 cold 是否也分區，也看不出來。
3. **Basic idea 第二、第三支箭頭**：沒有標籤。第一支是動作（Compress），後兩支看起來是「所以」的因果關係。意思猜得到，但同樣的箭頭混用了兩種語意。
4. **Who picks 的底色**：綠底是硬體、灰底是 OS，圖例沒有說明（見第 8 節）。
5. **Option B 的 Hot 變窄**：After 的 Hot 目測比 Before 窄一成多，但它是白色、未壓縮。我會短暫懷疑 hot 頁是不是也縮了。Option C 的 Hot 就維持原寬，所以判斷是畫得不精確。
6. **Cold 的壓縮幅度**：B、C 的 Cold 目測縮成約三分之二寬，A 的 Page 縮成約一半，而 Basic idea 寫 2:1。我不確定這是刻意表達 cold 頁壓得比較差，還是畫得不精確。

## 3. 圖說的一句話

把頁面壓小就能空出 DRAM 放更多頁，而三種做法的差別在於壓哪些頁、由誰決定，以及 OS 看到的樣子。

## 4. 三種做法各省多少、怎麼省

- **做法 A**：硬體把每一頁都壓小，After 目測空出約一半的列寬；OS 看到的頁數比實裝 DRAM 多，所以空間是由 OS 當成更多頁來用。
- **做法 B**：硬體只壓 cold 頁、hot 頁不動，After 目測空出約四分之一；OS 同樣看到比實裝 DRAM 多的頁數，空間也是由 OS 當成更多頁來用。
- **做法 C**：OS 自己挑 cold 頁放進 compressed tier 壓小，目測空出不到四分之一，而且 Free 畫在 compressed tier 內；OS 看到的是一個 NUMA node 多出容量。我推論這塊 Free 只能放進 compressed tier 的頁，但圖沒有明說。

**三者省得一樣多嗎？** 看起來不一樣：A 最多，B、C 較少。這個推論來自「A 壓全部、B 和 C 只壓 cold」，畫面也支持。有三點推論不出來：

- 圖上三個做法都沒有數字，實際省多少推論不出來。
- B、C 的省量取決於 cold 頁比例，圖裡的 2/4 是示意還是典型值，看不出來。
- B 和 C 都只壓 cold，但 Free 寬度目測不同（B 略大）。我推論不出這是真實差異還是畫得不精確，比較可能是後者。

## 5. 讀 Key takeaway 之後

Key takeaway 原文：Saved space comes from storing pages smaller; the options differ in which pages shrink and who picks them

**畫面與結論：一致。**

- 「Saved space comes from storing pages smaller」對應 Basic idea 和每欄的 After。
- 「which pages shrink」對應 every page 與 cold pages only。
- 「who picks them」對應 Hardware 與 OS。

有兩個不影響結論的小落差：

- 圖花了一整列畫 OS sees，結論沒有提，所以 C 與 A、B 在這一列的差異沒被收進結論。
- Option B 的 Hot 畫窄了，和「只有 cold 頁變小」略有出入。

## 6. 困惑指數

**2**。主線一看就懂，三欄也容易比較，只有 HRT 註解看不懂，另外有幾處寬度和底色需要停下來想一下。

## 7. 可疑的錯字或多餘文字

- 沒有看到拼字錯誤。
- **徽章「2」與檔名 01 不一致**：單看這張圖無法判斷哪個才對，建議確認。
- **HRT 註解**：縮寫未定義。對第一次學的讀者來說是多餘的雜訊，除非系列其他圖有解釋。

## 8. 顏色與圖例的意義是否一致

**部分一致。** 頁面本身的顏色完全照圖例走：白色未壓縮、綠色已壓縮、虛線是 free。問題在頁面以外的元素：

- **綠色有兩種意思**：頁面的綠色是「已壓縮」，Who picks 的綠底看起來是「硬體」。Option C 最明顯，綠色頁面配灰色 Who picks 列，所以綠不可能同時代表兩者。
- **灰底不在圖例裡**：從 B、C 對照可以猜出代表 OS，但這是猜的。
- **白色實線方塊不只代表頁面**：Free DRAM stores more pages、OS sees 這些文字框也長得和「Uncompressed page」圖例一樣。靠文字可以分辨，不太會誤導。
- 箭頭、Key takeaway 標籤和標題線的綠色只是裝飾色，不影響理解。

## 9. 能用自己的話說出結論嗎

可以。壓縮並沒有變出 DRAM，而是讓每頁佔得比較少，空出來的 DRAM 可以再放別的頁，所以看起來比實裝的多。A 由硬體壓全部的頁，省最多；B 由硬體只壓 cold 頁，hot 頁不動；C 由 OS 把 cold 頁放到獨立的 compressed tier，OS 看到的是 NUMA node 多了容量，不是單純頁數變多。

## 10. 總表

| 項目 | 結果 |
|---|---|
| 困惑指數 | 2 |
| 角色是否清楚 | 是（唯一例外是 HRT 註解，它不是圖中的主要元件） |
| 畫面與結論是否一致 | 一致 |
| 圖有沒有回答「怎麼省到空間」 | 是（機制清楚；省多少沒有數字，「誰能用」要從 OS sees 推） |

## 11. 是否建議重生

**不建議重生。** 四個條件都沒有觸發：困惑指數 2、角色清楚、畫面與結論一致、問題有回答。

下面幾點不足以重生，如果之後剛好要改這張圖，可以順手處理：

1. 確認徽章「2」與檔名 01 哪個才對。
2. 定義 HRT，或拿掉這條註解。
3. Option B 的 Hot 維持和 Before 同寬。
4. Who picks 不用頁面的綠色，避免同色兩義。
