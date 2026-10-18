# 运行接口：配置、证据与成片

Python 3.10+；Pillow、NumPy；FFmpeg/ffprobe；可用中文字体。支持 macOS/Linux，Windows 使用 WSL。`requirements.txt` 不含 FFmpeg；软件包不会自动安装依赖、下载模型或调用生成服务。内置 Imagegen 由具备该能力的 Codex 会话调用，CLI 不伪造其 API。公共包版本 `1.1.0` 新期使用 `workflow_version=2.2.0`，继续支持已冻结的2.1合同；更新运行时代码会生成新的run并要求对受影响的结果重新审查，不回写旧示例。

## 第一次运行

在仓库根目录运行 `python3 studio.py doctor`。默认优先使用仓库内许可字体 `assets/fonts/NotoSerifSC-VF.ttf`，也可设置 `STUDIO_FONT`，或在 `brand/profile.json` 中设置 `subtitle.font_file`。字体需覆盖实际文稿字符；doctor 找到字体不等于逐字字体检查通过。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python studio.py doctor
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python studio.py demo --output /tmp/video-studio-demo
```

demo 的输出目录必须为空或不存在。它会生成 10.8 秒工程样片：3 张程序化图卡、测试音、原创测试配乐、2 次叠化、不同位置的字幕和离线 QA。**测试音不是口播，图卡不是 AI 画作，生产审核记录继续 pending。** 内部工程入口不通过伪造 reviewer 来调用正式生产命令。输出 `DEMO-RESULT.json` 定位成片与证据。

## 项目和新期

默认项目根为这个仓库。要把制作资料放到另一个目录，在命令动词前添加 `--project /absolute/project`。代码和素材目录可以分离。

```bash
python3 studio.py init --slug your-topic --title '本期标题' --narration-file /path/script.txt
# 或：
python3 studio.py --project /path/project init --slug your-topic --title '标题' --narration-file /path/script.txt
```

`init` 用文件锁分配 `episodes/ep-0001-your-topic/`。可附 `--source-file` 保留原始资料；否则原始资料就是传入文稿。它只冻结输入、品牌和工作流快照，**不写分镜、不生成素材、不批准任何阶段**。每个新制作 Session 使用一个新期目录；修订也新建目录，在 BRIEF 中记录父版本，原件保留。

项目设置：

- `brand/profile.json`：`name`、`palette.dark/light/accent`、`subtitle.font_file/size_ratio`；可覆盖 `subtitle.light_text/dark_text`。图像风格与 IP 由品牌文档和生图提示词落实，渲染器不自动识别人物或重绘图片。
- `brand/active-ip.json`：`status` 与 `references` 数组，每项 `{file, sha256, role}`。路径相对项目根，role 说明身份主图/侧面/局部/风格参考等用途；无角色的品牌允许空数组。
- `brand/production-defaults.json`：平铺的 episode 默认字段（不是 `episode_defaults` 嵌套）。新项目默认1080×1920、25fps、0.48秒叠化、字幕0.12/0.16秒淡入淡出、本地音频、`audio_output.mode=narration_only` 和可见首镜缓提亮；没有固定声线或行业配色假设。已有默认文件保持不变；若仅含旧 `bgm` 设置，新期初始化会据其enabled状态显式选择音频路由；已有2.1期本身不升级。

每期 `brand.json`、`generation/brand-snapshot.json`、`source/locked-inputs.json` 冻结实际输入。以后修改共用默认只影响新期。不要为了消除错误重写旧文件的哈希；需要更改时创建明确修订并重新审核受影响阶段。

## 命令顺序

以下以 `EP` 表示本期 episode.json 的绝对路径；所有命令需要显式指定本期。`validate`/`status` 也会写 run 配置快照，并非只读检查。

```bash
EP='/absolute/project/episodes/ep-0001-your-topic/episode.json'
python3 studio.py validate --episode "$EP"
python3 studio.py design --episode "$EP"
python3 studio.py signature --episode "$EP"
# 独立分镜审核真实返回已保存并与当前 plan/design/response SHA 绑定后：
python3 studio.py reviewed --episode "$EP"
# 音频节奏审核真实返回和 request-text 已绑定后：
python3 studio.py audio --episode "$EP"
python3 studio.py timing --episode "$EP"
python3 studio.py preview --episode "$EP"
# 根据计划生成/选择图片，完成真实逐图审核与授权记录：
python3 studio.py fetch --episode "$EP"
python3 studio.py preview --episode "$EP"
# 查看实际预演，若有视频须播放实际片段；保存当前哈希绑定的预演审核：
python3 studio.py render-ready --episode "$EP"
python3 studio.py render --episode "$EP"
python3 studio.py offline-review --episode "$EP"
# 独立检查最终字幕样张并填写 caption-layout-review.json 后：
python3 studio.py verify --episode "$EP"
```

外置项目的每条命令都加 `--project /absolute/project`。每次以输出 `Run:` 为准，不凭旧目录猜测。分镜/任务/配置/核心代码变动会产生新 run；素材内容变化使旧预演审核失效。相同 MiniMax 请求复用已验证缓存。`search` 仅可选检索 Wikimedia Commons；不会自动录用第一张图片。没有一个“把文章交给 all 自动生成一切”的入口。

## 单期 JSON 与路径

字段完整例子见 `templates/episode.example.json`，每镜计划见 `templates/visual-plan.example.json`。初始化后的 `assets`、`sentences` 和 `shots` 为空，必须由 Agent 根据真实文稿填充。

- `sentences[].text` 按顺序拼接必须等于锁定 `narration.txt`（仅忽略空白）。`captions` 的文字顺序必须一致，允许不显示标点；标题不会自动朗读。
- `sentences[].asset` 是该句第一张图；可用 `visual_cuts:[{caption:1,asset:"shot-02"}]` 在第2条字幕开始换图。caption 索引从0开始；按真实声音校时。
- 资产 `file/prompt_file/reference/generation_record/record_file` 与 `brand` 相对项目根。分镜 `task_file`、`visual_plan.file/review_file`、音频节奏文件相对本期目录。预演 `preview_file` 相对当前run。不得越出作用域。
- 审核分镜以 `visual_plan.expected_shots` 对每句与 visual_cuts 逐项对应。计划正文包含源句、意义类型、观众收获、呈现方法、选择理由、画面描述、任务文件、备用方法、字幕构图；不是一句英文生图提示词代替整个计划。

静图 `motion` 为 `gentle`（缓推拉）或 `static`。`kind` 支持：

- `generated`：原始输出、prompt、可选 reference、provider、model/seed（不可见则null）、generation_record。记录需真实输出SHA、实际promptSHA、全部参考路径/SHA、真实图片审核。用原生生图工具生成后保存，CLI不会自行生图。
- `prepared_image`：排版/拼贴/静态知识图；file＋record_file，记录实际制作来源、许可、修改及审核；不能冒充AI原始图。
- `commons`：明确选择的真实图片 URL、page、author、license及许可链接，真实照片/档案计划还需subject/relevance/rights_review；保留作品对象和出处。
- `video`：已有本地片段＋record_file；明确 `in_seconds/out_seconds`、`fit:contain|cover`、cover时 `crop_x/crop_y`、`audio_policy:discard`。不足长度不会偷偷循环，若允许末帧停留需 `end_hold_seconds/hold_reason`。实际片段须播放审核，图片预演不算播放。

字幕框采用最终画面归一化坐标 `[x,y,width,height]`。每镜 `caption_layout` 要有 `box,align,theme,max_lines,layout_group,reason,protected_regions`。它必须在安全边距内且不挡主体；单条字幕显示期间保持位置稳定，叠化时同时检查相邻画面。过长文字会报错要求自然拆分，不无限缩小字体。

## 音频：已有录音与 MiniMax

已有音频有两种实际接口：

```json
{"provider":"local", "wav":"episodes/ep-0001-topic/audio/recording.wav", "timestamps":"episodes/ep-0001-topic/audio/native-words.json"}
```

时间戳 schema 见 `templates/native-words.example.json`：每个 `timestamped_words` 项含 `word,time_begin,time_end`（毫秒，相对未加首尾静音的原始WAV）。字幕全文必须精确对应；不得用按总字数均分的猜测时间冒充原生时间。输入音频转换为24kHz单声道PCM；字幕边界切开单个时间戳词时才在该词内部插值。

也可每个 editorial caption 一个真实音频文件：

```json
{"provider":"local", "clips":[{"text":"第一句。","file":"episodes/ep-0001-topic/audio/01.wav","pause_after":0.4}]}
```

clips 必须与所有 sentences.captions 按顺序一一对应，逐文件测量时长，片间pause_after为0至5秒；末条不追加此停顿。用于人工录音/其他服务逐段配音，不能把任意完整音频按猜测切分后宣称对齐。

本地音频的实际字节也属于本期输入。`local_audio.source_signature(speech, root, require_exists=True)` 返回项目相对路径到SHA-256的映射；在真实音频审核中将其保存为 `audio/direction.json.local_audio_sha256`，并刷新 episode 的 `audio_direction.review_sha256`。整段模式同时绑定WAV和词时间戳JSON；分段模式绑定每个clip。任何文件被同路径替换都会改变run指纹，并使旧音频审核失效，需审核新字节。规划阶段尚未交付的文件可在输入manifest中为null，正式audio导入时必须全部存在且与审核一致；程序不会自动替审核补哈希。


可选 MiniMax 中国站：复制 `.env.example` 为 `.env.local`，填 `MINIMAX_REGION=cn` 和自己的 `MINIMAX_API_KEY`（也支持环境变量）。模型适配 `speech-2.8-hd`、`speech-2.8-turbo`；可用性/价格/声线ID需制作时核对官方文档。本包不使用旧价格宣称确定成本。

```json
{"provider":"minimax-cn","model":"speech-2.8-hd","voice":"YOUR_ACTUAL_VOICE_ID","speed":0.8}
```

音频节奏审核有两个待审核模板：[MiniMax 合成](../templates/audio-direction.example.json) 与 [本地音频导入](../templates/audio-direction.local.example.json)。本地模板示例采用 WAV＋词时间戳；逐段录音时把 `speech` 整体替换为本期的 `clips` 配置，不混用两种模式，并按上文绑定实际源文件哈希。模板本身不代表审核通过。保存真实子Agent task_id、raw返回文件和 response_sha256；MiniMax request-text 中仅允许保持原词的空白/原生 `<#0.60#>` 停顿标签，本地导入可用干净原稿；若导入已有 TTS，则保留原请求稿及合法停顿标签作为来源记录，不重新执行标签。`speech`参数、文稿、request、review均绑定；音色/节奏改变需刷新相应审核。无法委派时只能如实记录 `main_agent_separate_pass` 及工具不可用理由，不写虚构子Agent。当前适配器没有发音字典、语音克隆或音效生成功能。

付费请求按endpoint+payload全哈希缓存，文件锁防重复提交；超时/结果不明记录 `submission_unknown` 并停止，不自动重发。字幕下载失败保留已返回音频；检查状态后恢复，不删除缓存以“修复”。首次调用会消耗用户自己的API额度；仓库不会借用作者账户。内置生图可用性及账户额度由使用者自己的Codex账户决定。

## 音频输出、开头与验收

2.2默认 `audio_output:{"mode":"narration_only"}`：从干净 `narration.wav` 两遍校准至约-17LUFS，静音补齐尾部并封装；不读取曲库、不调用音乐混音、不输出备选配乐版。源旁白长于最终视觉时阻断，避免截断。`audio-output/report.json` 记录干净源/输出SHA、视频流一致性、响度和未试听状态，离线审核及发布门禁绑定该报告。2.1未指定路由时保留旧契约，`bgm:{"enabled":false}` 仍通过旧voice-only混音分支。

显式选配乐：设置 `audio_output:{"mode":"licensed_bgm"}` 并提供 `bgm`，例如：

```json
{"enabled":true,"catalog_file":"assets/music/catalog.json","default_track":"track-1","alternatives":[],"bed_lufs":-36,"fade_in_seconds":2.2,"fade_out_seconds":3}
```

支持1默认＋0至2备选；曲库 schema见 `templates/music-library.example.json`。每首必须有文件SHA、许可、来源、署名和改动披露；时长不足停止，不默默循环。口播校准后，配乐默认-36LUFS并随语音再压低约4dB，成片目标-17LUFS、true peak≤-1.5dBTP，保留独立声轨、测量和许可文本。数字合格不代替主观听感。发布时遵循选定曲目的署名条款，不只把署名藏在文件元数据。

可见开头：`opening:{"style":"visible_smooth_lift","initial_brightness":0.78,"seconds":0.8}`。首帧显示同一首镜，在0.8秒内用smoothstep提亮，保留时间线与结束淡出；亮度范围(0,1]，时长须为正。省略 `opening` 使用0.3秒黑淡入。它不是平台封面元数据接口，平台预览仍须实际发送检查。品牌角色与尾卡的选图规则见[首尾画面](finishing-and-delivery.md)。

`offline-review` 完整解码所有变体、抽查字幕首中尾/镜头切换/首尾画面、核对声压及变体视频流一致性。最终 `verify` 要求真实独立字幕审核绑定当前离线报告和全部文件SHA，输出 `film.mp4`、可选备选版、`captions.srt`、`narration.wav`、`qa/validation.json` 和不自动播放的 `index.html`。文件通过、Agent视觉审查、完整播放试听、人类接受是四种不同结论。

成片检查后由Agent完成[素材ZIP与已授权改稿对比](finishing-and-delivery.md)，给出实际下载链接和校验结果；渲染命令本身不自动创建这些附件。

## 已实现边界

保留了实践引擎的原生时间戳对齐、精确帧数叠化、柔化字幕、构图保护、混合素材、授权配乐和指纹门禁。公共适配移除了固定客户品牌/角色、历史素材目录、机器绝对路径、强制三曲及旧Kokoro模型路径。没有实现自动联网爬取任意视频、自动音乐许可判断、图像角色相似度评分、无工具环境下的Imagegen、自动发布社媒。必须由Agent完成创作与真实审核，代码负责执行与防止资料串期。
