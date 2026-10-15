# Codex Video Studio

在 Codex 中，把选题、品牌/IP、分镜、配音、生图和剪辑组织成一套可交接的视频制作流程。可用于 AI 科普、知识解释、读书观点、故事或品牌内容。角色和画风可以替换，也可以完全不使用角色。

这是 **Agent 制作技能 + 本地渲染工具**。Python 负责素材接入、时间线、字幕、混音、导出和技术检查；Codex 负责内容判断、工具调用、视觉审查和交接。图片生成与语音服务需要你自己的可用能力或素材，仓库不会把订阅额度当成通用 API。

## 先跑一个不付费的样例

先下载仓库 ZIP，或运行 `git clone https://github.com/AllenLiu8888/codex-video-studio.git` 并进入目录。

需要 Python 3.10+、FFmpeg/ffprobe 及项目声明的 Python 依赖。当前运行时面向 macOS/Linux；Windows 使用 WSL。先查看环境，再运行工程演示：

```bash
python3 studio.py doctor
python3 studio.py demo --output /tmp/codex-video-studio-demo
```

`demo` 用程序化样张和测试音频检查渲染链，**不是 AI 生成质量或自然配音的示范**。真实品牌示例见 [未见实验室短片与完整制作资料](examples/ai-explainer/README.md)。具体依赖、输入格式和命令以 [运行手册](docs/runtime.md) 与 `python3 studio.py --help` 为准。

## 在 Codex 里做第一期

下载**整个仓库**，以这个目录打开 Codex。仓库内 `.agents/skills/` 提供三个项目技能，它们引用同仓库的文档和工具，不能只复制一份 `SKILL.md`。若界面尚未列出它们，重开会话或明确让 Codex 读取相应文件。项目技能位置与发现方式可参照 [Codex 官方技能说明](https://learn.chatgpt.com/docs/build-skills)。

首次可以直接发：

> 使用本项目的 `$video-studio`。我要做面向非技术读者的 AI 科普系列，先建立简洁、亲近的品牌参考，角色可选。然后按下方文稿制作一版视频。遵循项目默认设置；只有实质冲突或未授权费用需要问我。保留来源、分镜、生成记录和最终检查。文稿：……

已有品牌后，每次只需发：

> 使用 `$video-studio`，沿用已确认的品牌和制作预设，按下面文稿创建新一期并完成本地成片。文稿：……

更完整的交接提示词在 [新制作会话 Prompt](templates/production-prompt.md)。已授权范围内可以持续制作；用户要求“只做方案/试听/图片”时，按该阶段交付。

## 流程与可替换的部分

```text
Idea / 受众 → 品牌与可选 IP 参考包
                        ↓
选题调研或运营文稿 → 事实与权限 → 内容分镜 / 方法路由 → 独立反审
                                      ↓
                         语音导演 → 配音与实际校时
                                      ↓
                    生图 / 合法资料 / 静态图解 / 必要片段
                                      ↓
                    构图字幕 → 预演 → 剪辑混音 → QA / 交付
                                      ↓
                         反馈 → 最小返修 → 版本沉淀
```

品牌、领域事实规则、声音、节奏、音乐和画幅是可替换配置。分镜先行、实测音频校时、可追溯素材、真实审查与阶段返修是通用机制。每片不需要用齐所有视觉方法。

已执行检查见 [分发验证](docs/release-verification.md)。

## 从哪里读

| 你要做什么 | 入口 |
| --- | --- |
| 看完整制作顺序与完成条件 | [工作流](docs/workflow.md) |
| 建立品牌 / 角色参考包 | [品牌系统](docs/brand-system.md) |
| 决定某句该用什么画面 | [方法路由](docs/method-routing.md) |
| 配置声音、图片能力与成本 | [生成服务与语音导演](docs/providers.md) |
| 做 AI 新闻、科普、讲书或故事 | [领域规则](docs/domains.md) |
| 判断素材、审核与版本是否有效 | [来源和验收](docs/provenance-and-review.md) |
| 使用命令、JSON、测试与导出 | [运行手册](docs/runtime.md) |

本仓库的通用代码与文字按根目录许可证使用。外部模型、声音、字体、音乐和用户素材保留各自条款；发布前使用本期的署名清单。请用自己的品牌资料，示例不是必须照搬的审美标准。

---

**English:** A repository-scoped Codex workflow for branded narrated videos: idea and identity design, scripts, storyboard routing, voice direction, media generation, editing and evidence-based delivery. `studio.py demo` is an offline engineering check. Real production uses your own available image tools, voice service or local audio, and licensed media. Start with `.agents/skills/video-studio/SKILL.md`.
