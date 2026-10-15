# 未见实验室：流畅的回答，一定可信吗？

[实际短片](showcase.mp4) · [独立视觉报告](showcase-project/episodes/ep-0001-evidence-first/reviews/caption-layout-agent.md)

完成日期：2026-10-16。这是独立虚构品牌的一次实际制作，用于展示可替换品牌与题材的流程。

- 成片：28.36 秒，1080×1920，25 fps，H.264/AAC，709 帧。
- 内容：4 镜、4 份不同素材、10 条字幕、3 次 0.48 秒叠化，0 个解释动效，无 BGM。
- 图像：3 张新生成的 Codex 内置图像，1 张原创排版落版。后台型号与 numeric seed 未知，不虚构数值。
- 配音：真实已生成的 MiniMax 中文示例，音色 `Chinese_wenrounvxing`，模型 `speech-2.8-hd`，speed 0.8；复现导入打包 WAV，不再次调用付费服务。
- 声音测量：综合响度 -17.10 LUFS，true peak -1.50 dBTP；这不是试听结论。

完整解码、时长、帧数、字幕覆盖、重复素材与转场数量检查通过。独立 Agent 实际查看 42 个抽样画面及16张放大单帧，字幕、裁切与采样转场无阻断问题。

**未执行连续动态播放与主观音频试听；人类接受仍为 pending。** 新使用者应在自己的环境完整听看后决定是否采用。本例不保证重新生图逐像素一致，也不代表所有平台 UI 遮罩都已验证。

## 核查与复用

- [技术检查](verification/technical.json)
- [离线证据](verification/offline-qa/report.json)：原图、三张联系表及 samples.json 一并保留。
- [时间线](verification/timeline.json)与[字幕位置](verification/caption-placement.json)
- [文稿与初审](review-initial.md)、[品牌 brief](brand-brief.md)

原稿、计划、生成记录和正式审核在 `showcase-project/episodes/ep-0001-evidence-first/`。渲染中间缓存不入 Git；验证资料从真实 run 原样复制。

影片 SHA-256：`4a8c9253005d48f11e8ed0e44e2328783a2b6cfca4ae6e7b9763178a6e0716d3`。

## 使用权与事实来源

这是本项目原创示例；字体按 SIL OFL 1.1 使用。生成图像、合成声音的使用还需遵守相应服务条款；不包含声音模型或克隆权的转授。没有第三方背景音乐。事实来源链接与核查日期保留在本期 research 和审核记录中。
