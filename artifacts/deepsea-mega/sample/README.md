# s01 sample — 巨物恐懼 Wan 接長（3 段，205 格 @24fps ≈ 8.5 秒）

- `s01-start-image.png`：起始圖（z-image-turbo，1280×720，seed 42）
- `s01-wan-832x480.mp4`：Wan 原檔（接長後）
- `s01-wan-1080p.mp4`：放大版（ffmpeg lanczos + unsharp 5:5:0.7，CRF 17）

起始圖 prompt（前綴為頻道深海插畫風）：
A tiny camera rig with a small strobe light hangs on a cable in the upper left of a vast pitch-black abyss, a faint teal glow around it, marine snow drifting, far below at the edge of the glow a colossal dark curved shape is barely visible, immense scale, mostly empty black water, no eyes, no creature close-up

Wan 三段（negative: face distortion, morphing；832×480、69 格、20 步、guide 5.0、seed 42；後段起始圖＝前段最後一格）：
1. slow camera descent, marine snow drifting upward past the lens, the small strobe pulses softly, the huge dark curved shape far below stays almost still, pitch black water
2. the camera keeps sinking slowly, the enormous dark shape below drifts sideways into the faint edge of the glow showing only a vast curved wall of dark skin, marine snow, very slow and heavy, no close-up
3. the giant shape glides slowly past beneath the light and fades back into the black, the tiny strobe shrinks in the corner, marine snow drifts upward, calm awe

牆鐘：881.7 + 962.1 + 1083.2 = 2927 s（約 48.8 分）。

自評（🟡 我看了 4 格，Leon 請自己看影片）：前 3 秒乾淨、尺度感成立；第 2、3 段漸漸出現水紋／雜訊漩渦（接長的誤差累積），巨大形體只是一道靜止弧線，沒有「浮現再掠過」。接長適合 2 段（≈5.7 秒）；3 段要靠更保守的 prompt 或每段重新校色。
