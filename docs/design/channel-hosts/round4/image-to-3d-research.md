# 單張圖轉 3D：在這台 M5 32GB 上可不可行（只調查，不實作）

2026-10-17。調查由 subagent 用 WebSearch／WebFetch 完成，我整理成中文；**證據等級沿用它的標記**：🟢 讀過一手來源（附網址）、🟡 二手、🔴 未驗。我自己沒有重讀這些網址，所以整體對我而言最多算 🟡；要拿來做授權決定的，請以網址原文為準。

## 結論

- 本機可以做 3D，但授權乾淨的選項，在 Q 版吉祥物上的品質或適用性都有問題。
- **最低風險的仍是現在的 2D PNGtuber 路線**：不需要額外授權，也不用清理網格。
- 如果真的要試 3D：
  - 先試 **SF3D**：授權免費門檻是年營收 ≤ US$1M，支援 MPS，輸出 GLB。用 3 張圖驗證卡通角色的品質，再決定要不要投入。
  - **不要用 Hunyuan3D 2.1** 做營利頻道：授權明文不適用於歐盟、英國、南韓。
  - **TRELLIS.2** 品質最好，但社群 Mac 移植版預設綁了一個非商用的去背模型（RMBG-2.0，CC BY-NC），另一個依賴 DINOv3 是 Meta 自訂授權。這兩個要先換掉或核清楚，才能商用。

## 模型比較

| 模型 | 授權／商用 | 在 Mac 上 | 記憶體／時間 | 輸出 | 備註 |
|---|---|---|---|---|---|
| Hunyuan3D 2.1 | 🟢 Tencent Hunyuan 3D 2.1 Community License（[LICENSE](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE)）。原文：「DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA」；月活超過 100 萬要另外授權；第 5(b) 條禁止用輸出去改進其他 AI 模型 | 🟢 README 寫支援 macOS，但沒有 Apple Silicon 的步驟；貼圖要 CUDA 自訂 rasterizer。🟡 有社群 MPS 移植版，未驗 | 🟢 形狀約 10 GB，加上貼圖共約 29 GB | 網格＋貼圖 | 授權有地區排除，營利頻道不可用 |
| Hunyuan3D 2.0／2mini／2mv | 🟡 同系列社群授權，LICENSE 原文沒讀到 | 🟢 README 寫支援 macOS，但沒提 MPS | 🟢 形狀 6 GB，形狀＋貼圖 16 GB | trimesh，可存 .glb | 模型較小，可能比較好移植；未驗 |
| TRELLIS.2（Microsoft） | 🟢 程式和模型是 MIT（[repo](https://github.com/microsoft/TRELLIS.2)）；🟡 依賴的 DINOv3 是 Meta 自訂授權，RMBG-2.0 是 CC BY-NC 4.0 | 官方只支援 CUDA（需要 24 GB 以上 NVIDIA）。🟡 社群移植 [trellis-mac](https://github.com/shivampkumar/trellis-mac) 改用 MPS／Metal，成熟度不明 | 🟡 移植版建議 24 GB 以上統一記憶體，峰值約 18 GB，M4 Pro 約 5 分鐘，熱降頻時會慢很多 | GLB＋PBR 貼圖 | 品質最好；要換掉非商用依賴才能營利 |
| Stable Fast 3D（SF3D） | 🟢 Stability Community License：年營收 ≤ US$1M 免費，超過要買 Enterprise（[HF](https://huggingface.co/stabilityai/stable-fast-3d)） | 🟢 支援 MPS，但標為實驗性，要設 `PYTORCH_ENABLE_MPS_FALLBACK=1`；統一記憶體不到 32 GB 時建議用 CPU，我們剛好在門檻上 | 🟢 約 6 GB，不到 1 秒（官方數字） | GLB，有貼圖和 UV，低面數 | 最快、門檻最低；卡通品質未驗 |
| SPAR3D | 🟢 同 Stability Community 授權，HF 卡上的門檻寫法前後不一致 | 🟢 同 SF3D | 🟢 約 10.5 GB（另一處寫 6 GB，互相矛盾） | GLB | 大致被 SF3D 取代 |
| TripoSR | 🟢 MIT（[LICENSE](https://github.com/VAST-AI-Research/TripoSR/blob/main/LICENSE)），沒有商用限制 | 🔴 MPS 支援未查 | 🟡 A100 約 0.5 秒 | 網格 | 授權乾淨，品質較舊、較弱 |
| InstantMesh | 🟢 頁面標 Apache-2.0，LICENSE 原文沒讀 | 🟢 需要 CUDA ≥ 12.1 和 xformers，硬性綁 CUDA | — | OBJ | 不移植就不能在 Mac 上跑 |

## 綁骨架要多少工

- 圓胖青蛙、金魚、瓶子這類角色，要做眨眼、開閉嘴、歪頭、擠壓伸展，**用 shape key（blend shape）加物件變形就夠，不需要骨架**。
- 自動綁骨架工具：
  - Mixamo 只支援人形（🟡）。
  - UniRig 是 MIT 授權（🟢），但需要 CUDA 和 8 GB 以上 VRAM，這台 Mac 不能用。
  - Blender Rigify 以人形範本為主（🟡）。
  - Anything World、RigNet 沒有查（🔴）。
- 工時（🔴 都是估計，沒有實測）：
  - shape key 綁定（眨眼、3–4 個嘴型、擠壓）：Blender 新手約 4–8 小時。
  - 用骨架加自動權重：約 6–12 小時。
  - 清理 AI 產生的網格（補洞、重拓撲、貼圖接縫）：另外 2–4 小時。

## 對我們的意義（我的判斷 🟡）

- 這次的「3D 質感」走的是另一條路：**用 klein 把 2D 角色重畫成 3D 渲染風格**，再加上 2.5D 深度動作（見報告第四輪）。授權沿用 klein 4B（Apache-2.0）和 Depth Anything V2 Small（Apache-2.0），沒有新的授權風險。
- 真的 3D 網格只有在要「轉身、多角度、做周邊公仔」時才划算。到那時，建議請繪師或 3D 師依定稿製作，並在合約裡寫明著作財產權讓與，而不是走 AI 網格。
