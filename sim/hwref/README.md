# hwref：LZ4 硬體的 reference model

RTL 要逐 byte 重現的行為，寫成可以執行的 Python。硬體設計規格 `spec/lz4-hw-design-spec-v0.md` 由這裡產生，裡面的表格、範例、pseudo code 與數字都直接取自這些 model。

沒有時間、沒有 ring、沒有 register。Ring 與 register 的行為在 `ifsim/hw.py`，kernel 的控制程序在 `hostsim/kernel.py`。Descriptor 與 completion 的 byte 格式沿用 `ifsim/interface.json`。

## 執行

```
python3 sim/run_hwref.py gen-doc                    # 重新量測並產生 spec/lz4-hw-design-spec-v0.md 與 .json，約半分鐘
python3 sim/run_hwref.py gen-doc --reuse            # 只改了文字或 model 的註解時，用存好的數字重建文件
python3 sim/run_hwref.py study                      # 印出各種 encoder 變體的 stream 長度與 cycle 估計
python3 sim/run_hwref.py study --n 1000 --json      # 每組 1000 個 page，JSON 輸出
python3 sim/run_hwref.py vectors --out DIR          # 寫出給 RTL test bench 的 vector，約 3.5 MB
cd sim && python3 -m pytest tests/test_hwref.py     # 這些 model 的測試，約 2 秒
```

## 檔案

| 檔案 | 內容 |
|---|---|
| `lz4core.py` | `encode`、`decode`、`crc32`，以及基準架構的 cycle 估計。RTL 的 encoder 輸出要與 `encode` 逐 byte 相同 |
| `job.py` | 一個 descriptor 進去之後：五項檢查、哪些記憶體被讀寫、completion 的 16 B、哪些範圍有定義、哪些 access 被授權 |
| `study.py` | 四組 page 上比較 hash table 大小、hash 函式、寫入規則，並與 liblz4 對照；整個 job 的 cycle 估計 |
| `vectors.py` | Encoder、decoder、壞掉的 stream、job 四類 test vector，以及規格裡那個範例的 page |
| `doc.py`、`templates/` | 產生設計規格。文字在 template，表格與數字由程式填 |
| `__main__.py` | 命令列 |

## 能回答與不能回答

能回答：任何 page 壓出來的 stream 是哪些 byte；任何 byte 串解不解得開、哪一項檢查失敗；一個 job 之後記憶體與 completion 的樣子；encoder 的參數對 stream 長度的影響。

不能回答：實際的 cycle 數與 clock 頻率，這裡只有照基準架構數出來的估計；面積與 timing；bus 上有其他 master 時的行為。這些要等 RTL。

## 注意

- Heap 那一組 page 取自執行量測的 Python 程序自己的記憶體，每次執行內容不同，數字會有 1% 左右的浮動。`gen-doc --reuse` 不重新量測。
- `bus_*` 的 job vector 依據設計規格的提案 P2，介面規格還沒有收進去。
- `job.py` 在 BAD_STREAM 時不寫 frame，RTL 的基準做法是邊解邊寫。Model 把 frame 標成未定義，所以兩種做法都符合。
