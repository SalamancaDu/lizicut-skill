# 辅助工具与 FFmpeg 时间线

## 选择本次实际可用的路径

默认主流程使用 [Premiere 执行](premiere.md)，已有 PR 工程从副本接续。此处的 Python 工具可辅助素材落盘、字幕重映射及媒体检查；只有用户选择本包合成器或其他执行端时才建立下面的 FFmpeg 时间线。不要因为 MCP 缺失或失败自动切换执行端，也不要要求 PR 任务重复维护一份 FFmpeg 工程。

用户选择本地图片/视频合成路径时，使用 Python 3.10+ 标准库及 PATH 上已有的 FFmpeg / ffprobe。合成器支持主画面、独立叠层、音频源区间、透明淡入淡出、BGM 按旁白/原声区间平滑降低、纯文本 SRT 与 H.264/AAC MP4。连接处为硬切，复杂运动与转场先在可控工具中制作。它不提供 PR 工程生成器。

未具备的搜索、ASR、对齐、配音或生成能力应说明具体缺口并完成可独立交付的部分。不得为了分类偷偷调用另一个模型，不自动安装依赖、上传素材或调用付费服务。素材检索与候选判断沿用当前可用工具；本包的 [materials 入口](material-search.md#助手合同与用法)可下载已选直链、导入本地文件、检查媒体并保留来源，输出能合入时间线的 assets 与镜头绑定，未回填前不算已剪入。

## 时间线最小例子

仅使用本包合成器时需要这份 JSON。文件路径相对时间线文件本身；也可用本机绝对路径，但开源示例应使用相对路径。以下路径用于说明合同，实际渲染前必须准备对应文件。

```json
{
  "version": "lizicut.timeline.v1",
  "project": {
    "title": "解释示例",
    "width": 1280,
    "height": 720,
    "fps": 25,
    "duration_ms": 4000,
    "timing_basis": "fixed",
    "audio_mode": "silent",
    "background": "#20221f"
  },
  "assets": {
    "board": {
      "path": "assets/board.png",
      "kind": "image",
      "source_type": "designed",
      "source_ref": "由用户提供的原稿设计；此处为示意",
      "usage": "illustration",
      "license": "original"
    }
  },
  "shots": [{
    "id": "shot-01",
    "start_ms": 0,
    "end_ms": 4000,
    "asset_id": "board",
    "source_in_ms": 0,
    "fit": "contain",
    "carrier": "graphic",
    "information_shape": "comparison",
    "purpose": "让观众看清两个状态的差异",
    "decision": "同尺度并排；不需要额外素材或切镜",
    "evidence_refs": []
  }],
  "audio": []
}
```

## 合同要点

- 项目宽高为 16—3840 的偶数，fps 为 1—60 整数。素材帧率可不同，合成时统一。项目时长用 duration_ms 或 duration_frames 二选一；shots / overlays 的每条边界用 start_ms + end_ms 或 start_frame + end_frame 二选一，同一处混填会报错。范围均包含起点、不包含终点。主画面按帧连续并覆盖整片；源入点仍用 source_in_ms。
- 24/30/60fps 等非整毫秒帧周期优先使用帧号。例如30fps两秒影片填 duration_frames=60，一帧主镜头填 start_frame=0、end_frame=1。毫秒字段也可写有限小数，但视频边界只容忍1微秒的数值表示误差；33ms不能冒充30fps的一帧。既有25fps整数毫秒时间线保持可用。项目长度须覆盖声音尾部，必要时向后补齐末帧；不要为了通过校验将真实语音切点静默挪到最近视频帧。
- `timing_basis` 为 estimated / aligned / fixed。estimated 可做结构校验，但不能由本合成器导出正式视频。aligned 表示已有经校对的声音时间；fixed 适用于明确设计的固定时长，包括无解说配乐或静音视频。字段是作者声明，脚本不能证明转录真的正确。
- `audio_mode` 为 narrated / original / nonverbal / silent。前两种分别要求增益大于零的 narration / original 声音轨；nonverbal 用于无解说的图文配乐，仅允许 BGM/SFX，且至少一条增益大于零；silent 要求没有声音轨。它不能从角色声明证明音源含真实语音。静音 MP4 包含静音 AAC 轨，避免播放端行为不一致。
- assets 的 kind 为 image / video / audio / subtitle。source_type 为 user / document / stock / generated / designed / synthetic_audio；usage 为 evidence / illustration。`generated` 和 `synthetic_audio` 不得充当事实证据；原样素材和自制图表的来源仍需人核查。
- 每镜的 carrier 为 host / footage / graphic，information_shape 为解释关系名称，不是互斥模板资格。purpose 与 decision 用于保留剪辑理由，合成器不会把这些自然语言自动转成动作。
- 图片持续到镜头结束。视频从 source_in_ms 播放，长度不足时报错。fit 为 contain（保全）或 cover（允许裁切），按包含像素宽高比的显示比例适配，再输出方形像素；非方形像素视频不会直接按存储尺寸拉伸。主镜头的透明与半透明区域先和 project.background 合成，再编码为不透明 MP4；contain 留边也使用该背景色。loop 只有明确为 true 才循环，且从源文件零点开始；局部循环先制作裁好的素材。
- 使用每个源文件的第一路视频/音频流，在容器共同起点下分别校验其起止位置；不把各流单独归零，也不拿较长的视频流掩盖较短声音流。原有音频延迟用静音保留；请求的视频范围早于第一帧或必要时间信息不明时先准备同步主素材。原有同步偏移与人为安排的时间线位置分别处理。
- evidence_refs 引用 assets 中 usage=evidence 的素材；不能把插画引用成事实依据。来源地址记录在 source_ref，合成器不联网验证来源或下载。
- 未知执行字段会报错，避免静默忽略尚未支持的效果。

## 独立叠层

`shots` 是连续主画面，也可作为背景。可选顶层 `overlays` 按从后到前排列，主画面在其下，字幕在所有叠层之上。叠层之间允许重叠和空缺；每层的时序与主画面独立，起止在帧栅格上。

```json
{
  "overlays": [{
    "id": "keyword-01",
    "asset_id": "prepared-label",
    "role": "template",
    "start_ms": 800,
    "end_ms": 4000,
    "x": 120,
    "y": 160,
    "width": 640,
    "height": 240,
    "fit": "contain",
    "opacity": 1,
    "fade_in_ms": 200,
    "fade_out_ms": 160,
    "purpose": "听到关键关系时完成揭示",
    "decision": "已准备好透明标签，在背景建立后进入，与单元共同退出"
  }]
}
```

此片段应并入完整时间线，并在 assets 中声明真实的 `prepared-label` 图片/视频文件。role 为 element / template；位置与尺寸为项目像素，矩形不能越界。contain 的空余区透明，cover 会裁切。opacity 为 0—1；淡入与淡出相加不得超过图层长度。`source_in_ms`、`loop` 和 `evidence_refs` 与主画面含义相同。素材有 alpha 时保留透明区域；没有 alpha 的视频按不透明矩形处理，不执行自动抠图、圆角、移动、缩放或文字排版。这些效果先制作成所需素材。

需要逐帧入场时，用 start_frame / end_frame 替换这条叠层的 start_ms / end_ms。执行器以整数帧定位预制动画并控制可见区间，保留首状态；不会用浮点秒偏移再截断首帧。对重要揭示仍检查入场前一帧、首帧及退出帧，声音落点单独保留在 audio 的真实时间中。

主镜头和叠层共用显示比例适配。标记 alpha_mode=1 的 VP8 / VP9 WebM 分别使用 libvpx / libvpx-vp9 解码器，避免默认解码器丢失透明通道；缺少所需解码器时在渲染前报出素材与能力缺口，先使用已有工具准备无损 RGBA 素材或补齐所需环境，不导出不透明替代品。PNG 原始 alpha、图层 opacity 和淡入淡出共同作用；普通黑底视频不会自动变透明。仍须检查实际导出的边缘、遮挡和可读性。

## 音轨

视觉源的声音不自动保留。需要主播原声、现场声或旁白时显式加入 audio；每条轨的源时间与成片时间分开：

```json
{
  "id": "voice-01",
  "asset_id": "recording",
  "role": "narration",
  "start_ms": 0,
  "end_ms": 4000,
  "source_in_ms": 1200,
  "gain": 1,
  "fade_in_ms": 20,
  "fade_out_ms": 40,
  "loop": false
}
```

role 可为 narration / original / bgm / sfx；asset 可以是音频文件或带声音的视频。start/end 是成片位置，source_in 是源入点，三者允许有限小数毫秒；所需源长度等于 end-start。声音按48kHz采样点落位，不因画面帧号改变源时间。gain 在 0—2；淡入和淡出相加不超过轨长。多段粗剪可重复使用同一个源文件，以不同源入点映射到连续成片位置。

BGM 可以增加 `duck_gain: 0.45`，表示在 narration / original 主声音轨区间降低到原 gain 的 0.45 倍。默认提前 80ms 下降（`duck_attack_ms`），结束后用 240ms 恢复（`duck_release_ms`），相距不超过 300ms 的声音段合并保持降低（`duck_hold_ms`）。三个值可调整：attack/release 为 1—5000ms，hold 为 0—5000ms，必须与 duck_gain 同用。这些是本助手的初始包络参数，不是原项目的冻结规则或响度标准。

合成器不检测句内语音活动；原声若只是环境气氛，不希望整段压低音乐，可不使用 duck_gain，改为显式分轨或准备好的包络。背景循环从源零点开始，需要局部循环时先制作裁好的音频文件。

混音尾部补静音到项目长度，限幅用于避免峰值越界，不代表已经做 LUFS 响度匹配。必须回听实际结果。

## 字幕

资产声明 `kind: subtitle`，顶层添加：

```json
{
  "captions": {
    "asset_id": "captions",
    "font_name": "Microsoft YaHei",
    "font_size": 32,
    "margin_bottom": 36,
    "margin_side": 40,
    "max_lines": 2,
    "max_cps": 21,
    "min_duration_ms": 900,
    "max_duration_ms": 6000
  }
}
```

SRT 为 UTF-8、成片时钟、按序不重叠，支持显式换行；源/成片尾部允许不超过0.5ms的SRT取整误差，重映射输出仍限制在实际成片时长内。字幕字体必须在目标机器可用；换平台时选择正确中文字体并检查真实画面。烧录转换使用 ASS，时间精度为 10 毫秒；本路径拒绝字幕正文里的 `{`、`}`、反斜线，避免控制序列改变原文。需要原样呈现这些字符或复杂字幕效果时使用合适的其他后端。

validate --media 与 render 都会逐条检查字幕。经过 ASS 时间转换后没有任何可见视频帧的字幕、显式行数超过 max_lines 的字幕会在渲染前报错，不生成截断替代品。按字符宽度估算的自动换行/块高度、阅读速度与停留时间超限则返回带条目编号的 warnings；估算不是字体实测，仍需检查实际画面。

上述预算是原项目的可调起点。max_cps 按非空白字符/秒计算；字号、画幅、语言、平台及普通字幕/逐词字幕的用途会改变合理预算。先按真实语义和声音拆准确子句，或调整阅读保持、版面、字号与侧边距；仅有句级时间时不均分猜词，也不靠无限缩字或调高行数掩盖裁切。确需短词字幕可调整 min_duration_ms，但始终检查是否实际显示。处理每项告警，或依据实际字体画面与声音说明为何保留，才能报告该字幕环节完成。

## 命令与保护

从 Skill 目录执行，或将 scripts 路径换成实际 Skill 所在位置：

```text
python scripts/lizicut.py doctor
python scripts/lizicut.py validate timeline.json
python scripts/lizicut.py validate timeline.json --media
python scripts/lizicut.py retime-captions original.srt cuts.json --output captions.srt
python scripts/lizicut.py render timeline.json --output output/film.mp4 --threads 2
python scripts/lizicut.py inspect output/film.mp4 --decode
```

默认拒绝覆盖已有输出；只有明确需要更新同一输出时才用 `--overwrite`。任何输入文件都不能被输出替换。渲染只清理本次创建的临时目录，失败时不修改源素材。主画面逐镜统一规格后合成，默认限制 2 个编码线程；长片先评估本地空间和时间，避免无必要的多次渲染。

过滤图超过 8000 字符时，助手用 `-/filter_complex` 从临时文件读取，避免 Windows 命令长度限制；这一分支已在本机 FFmpeg 9 验证。旧版 FFmpeg 若不支持该选项，应先按段预混声音/预合成复杂画面来减少输入，或使用已有的合适后端；不自动升级环境。很多独立输入仍有文件句柄、路径总长和内存成本，不能把短例验证当作长片性能证明。

## 交付与检查

正式视频需要：素材可读、声音时钟已确定、字幕已校对、画面完整、各层按同一时间线编排。导出后检查真实尺寸、时长、音轨及完整解码；抽看首中尾、切镜与复杂板面，并回听所有新切口。相应片段发生修改时只重验受影响部分及实际最终文件。

技术检查通过后，单独判断解释关系是否准确、中文是否读得完、图表是否同口径、证据身份是否清楚、音乐是否压人声。没有独立人工审片就明确为作者自检。不要把脚本输出 valid/decoded 解释为审美验收。

## 口播粗剪入口

用于已核对的单一主录音/主播视频；已有剪辑工程优先沿用。双机视频和独立收音先在已有工具同步，不能给不同源文件直接套同一入点。本助手使用源文件第一路音频/视频，不自动选麦克风、做 ASR、判定重复或修复跳切。

先按[口播规则](timing-and-roughcut.md)决定删什么，再写 lizicut.roughcut.v1 计划。下面是合同示意，不是对某份录音的分析结论；路径和决定须换成实际素材与证据。

    {
      "version": "lizicut.roughcut.v1",
      "title": "口播粗剪",
      "source": {
        "path": "recording.mp4",
        "kind": "video",
        "source_type": "user",
        "source_ref": "用户提供的同步原片",
        "license": "user-provided"
      },
      "source_duration_ms": 6000,
      "video": {"width": 1280, "height": 720, "fps": 25},
      "captions": "source-captions.srt",
      "splice_fade_ms": 5,
      "decisions": [
        {
          "id": "take-a",
          "start_ms": 1000,
          "end_ms": 2000,
          "action": "remove",
          "category": "retake",
          "reason": "替代段事实一致、表达完整且前后可接",
          "evidence": "记录实际核听/对齐依据，不填占位式已检查",
          "timing_checked": true,
          "related_keep": {"start_ms": 2000, "end_ms": 3200},
          "visual_note": "检查头部与手势；尚未覆盖跳切"
        },
        {
          "id": "keep-breath",
          "start_ms": 3400,
          "end_ms": 3600,
          "action": "protect",
          "category": "breath",
          "reason": "这是下一句需要的正常换气",
          "evidence": "记录实际声音和前后语境依据"
        }
      ]
    }

- source_duration_ms 是源时钟从零到实际可用末尾的长度，与媒体探测值允许1ms误差；视频还须对应实际帧末尾，必要时填小数毫秒，不能先取整丢掉分数帧。所选流的结束位置为“相对共同零点的起点 + 流时长”；音频模式取声音结束位置，视频模式取音视频较早的结束位置。例：视频0—3000ms，音频500—3000ms，则填3000而非2500，前500ms保留静音。视频必须在源零点有画面；缺帧或时间异常先准备同步主素材。去掉片头/尾也显式记录删除，不能少填全长静默丢尾部；只剪某窗口时先准备有明确来源的该段主素材。
- source.kind 为 video / audio，source_type 可沿用素材合同的来源类别。音频模式省略 video；视频模式显式给尺寸和整数 fps，通常沿用原片规格。需要分数帧率、特殊时间码或独立多轨同步时沿用合适的已有后端；此助手要求源切点也在项目帧网格上，不暗中取整语音边界。
- 粗剪计划仍使用源毫秒，可填有限小数；30fps的第1、2帧边界可由帧号计算为33.333333333333336、66.66666666666667毫秒。视频保留区间与成片累计位置按帧计算，避免逐段取整累积漂移；音视频共用这些精确源区间。SRT 重映射才取最近整毫秒，末尾限制在成片时长内，不改写文字。无法确定原片帧边界时保留待复核或使用已有合适后端。
- action 为 remove / protect / review：未列出的内容、protect 和 review 均保留。任何删除与保护/待复核区间相交都会报错；要改变决定，先依据证据修正计划，不绕过保护。
- category 为 retake / redundancy / self_correction / filler / pause / breath。前三类语义删除必须给 related_keep 指明保留表达，且该区间不能再被别处删除。程序只核对区间关系，无法证明两段语义相同或哪段更好。
- 每条决定有 reason 与 evidence，分别说明为什么这样剪、根据什么判断。remove 还要求 timing_checked=true；这是智能体已核对时间的声明，不是用户逐刀审批。只有文本相似、未经校对的 ASR 或低电平波形时，不能冒称已核听。
- captions 可省略，提供时必须是源时钟的真实 SRT。跨删除边界的字幕会指出具体条目，要求依据声音拆分；不猜词、不改写。字幕单独交付，粗剪预览默认不烧录，方便继续精剪；需要烧录时在生成时间线添加现有 captions 配置。
- visual_note 只记录切口要处理什么，不会自动变成 B-roll、景别变化或转场。新素材实际加入 overlays 或 NLE 后才能报告已处理。splice_fade_ms 仅缓和内部音频接缝，范围0—20ms，不改变映射，不是呼吸处理或听感保证。

按实际需要选择只准备或准备并导出：

    python scripts/lizicut.py roughcut roughcut-plan.json --output-dir output/roughcut
    python scripts/lizicut.py roughcut roughcut-plan.json --output-dir output/roughcut-preview --render

第一条生成编辑数据，第二条还实际导出。输出目录必须是新的，不覆盖已有工程。所有源素材、决定与字幕检查在建目录前执行；媒体渲染失败时保留已生成的编辑数据，错误中说明位置，不将它宣称成已完成的预览。

输出 cuts.json 可供原有 retime-captions 使用；roughcut-map.json 保留源/成片映射、删减理由、切口、各流源时钟起止及保留的待复核位置。提供字幕时输出 captions.srt。视频还输出可修改的 timeline.json 和可选 roughcut.mp4，视频与同期原声严格使用同一源区间；音频则可输出48kHz双声道 PCM roughcut.wav。关联源文件不复制，保持原路径关系；交接或迁移时同时带上源素材。

这些 JSON 是本助手的编辑数据，不是 PR 工程文件。PR 主流程按 [Premiere 粗剪实施](premiere.md#从口播决定到-pr-粗剪)把同一映射落入实际序列并核查，交付真实工程、序列与标记；不先压平原始口播来替代可编辑粗剪。若保留硬切或待复核内容，应逐项说明。未经实际执行的覆盖、核听和人工审片不能标为完成。
