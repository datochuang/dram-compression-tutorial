# DRAM compression study

互動式文件：<https://datochuang.github.io/dram-compression-tutorial/>（GitHub Pages，從 `docs/` 發佈）

學習 SoC 上的 DRAM compression：一個 LZ4 的圖解說明，加上一個假想的 SoC（硬體 LZ4 加速器、CPU MMU、LZ4 MMU），
目標是省容量：所有 client 經過同一層壓縮，HRT 的記憶體不壓縮。

## 目錄

- `src/page.html`：說明文件的原始檔，含 `/*__CORE__*/` 佔位符，建置時嵌入 LZ4 程式。
- `src/build.js`：把 `docs/lz4-verify/lz4core.js` 嵌進 page.html、替每張有壓縮資料的 SVG 加 hatch pattern、
  在 DOM stub 裡跑完所有互動示範檢查錯誤，輸出 `docs/lz4-soc-explainer.html`。
- `src/figs9.py`：第 9 節五張 DRAM 圖的產生器，直接改寫 `src/page.html` 裡 `<!--fig9X-->` 標記後的圖。
- `src/shoot.sh`：用 headless Chrome 截圖或 dump DOM。
- `docs/lz4-soc-explainer.html`：建置結果，發佈到 claude.ai artifact 的版本（沒有 `<html>` 外殼，由發佈端包起來）。
- `docs/index.html`：同一份內容加上完整的 HTML 外殼，給 GitHub Pages 用；Pages 設成從 `main` 分支的 `/docs` 目錄發佈，網址是 <https://datochuang.github.io/dram-compression-tutorial/>。
- `docs/lz4-verify/`：LZ4 程式（`lz4core.js`）、與 `lz4` v1.10.0 的比對（`verify.js`）、量測腳本，
  以及 512 MiB 設計的所有數字（`plan512.py`）。
- `figures/capacity-approaches/`：sketchnote 圖的 prompts、產生紀錄與審查。

## 建置

```sh
cd src
node build.js          # 寫出 ../docs/lz4-soc-explainer.html，並走完所有示範
python3 figs9.py       # 只有改第 9 節的數字或圖時才需要，之後再 node build.js
python3 ../docs/lz4-verify/plan512.py   # 印出第 9 節到第 12 節用到的每個數字
```
