# 3D Printing Products

FDM 3D 列印產品 + PCB 電路設計的開發倉庫，從發想到銷售。

## 目錄

| 路徑 | 用途 |
|---|---|
| `products/` | 每個產品一個資料夾：規格、成本、設計決策、打樣紀錄 |
| `fusion360/scripts/` | Fusion 360 Python 腳本，一鍵生成參數化模型 |
| `electronics/` | KiCad 電路圖 / PCB / BOM / 供電計算 |
| `docs/` | 通用設計規則與流程（FDM 公差、選料、法規） |
| `tools/` | 計算與自動化腳本 |

## Fusion 360 腳本怎麼跑

Utilities → ADD-INS → Scripts and Add-Ins → Scripts → 綠色 `+` →
選 `fusion360/scripts/<名稱>` 資料夾 → 選腳本 → Run。

要改尺寸就改腳本頂端的 `CFG`，存檔後再 Run 一次。
模型是程式碼 → 可版控、可 diff、可複用。

## 現況

- `fusion360/scripts/ParametricBox` — 參數化收納盒 / 電子外殼（盒身 + 唇口式上蓋）。
  用途是驗證腳本管線，也是之後所有需要外殼的產品的基底。**尚未在 Fusion 實機驗證。**
