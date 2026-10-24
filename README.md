# Lizicut · 李子的解释型视频剪辑 Skill

把“这段话应该怎样剪”变成智能体可以执行的判断：先找解释任务，再组织画面、素材、声音与时间。默认以财经科普为主要场景，也支持商业分析、公司/行业机制和其他解释型内容。

当前版本为 **v0.2.1**。方法来自原 lizicut.com / SnapFilm 项目及三份剪辑思维导图，已去除旧网站运行依赖。完整代码、规则和自制示例按 MIT 开源。

[下载 v0.2.1](https://github.com/SalamancaDu/lizicut-skill/releases/tag/v0.2.1) · [Skill 入口](skills/lizicut/SKILL.md) · [许可](LICENSE)

## 从这里开始

| 你现在有什么 | 可以怎样调用 |
|---|---|
| 文案，先想清楚画面 | `使用 $lizicut，为这篇文案做解释单元、分镜和素材方案，先不生成。` |
| 文案和录音 | `使用 $lizicut，以这份录音为时钟，完成素材、字幕、音画编排并导出成片。` |
| 主播视频 | `使用 $lizicut，保留我的观点和自然停顿，先粗剪，再补必要的解释画面。` |
| 已有项目，需要修改 | `使用 $lizicut，只修改这段机制解释，沿用现有品牌、素材和时间线。` |

默认执行端是 Premiere Pro：先确认文稿和录音，再在独立工程/序列副本中完成口播粗剪、素材导入、图层与动效、字幕和声音对齐，最后由 PR 保存工程并提交导出。推荐使用具备本地 CEP 桥接的 [PremiereMCP](https://github.com/DutchErwin/PremiereMCP)；Skill 会先发现当前 MCP 的真实工具和参数，不把某个服务器名称当作固定接口。PS、Illustrator 和 After Effects 是按镜头需要选择的协作分支，保留可编辑源文件并将实际交接素材回到 PR。

PR 的编码导出依赖 Adobe Media Encoder 或当前 MCP 的实际导出能力。MCP 返回“已入队”不等于 MP4 已完成；必须检查输出文件、完整解码和首中尾同步。没有可用 AME 时，报告导出缺口，不悄悄用 FFmpeg 代替 PR 成片。

也可在安装前，直接让智能体读取本项目的 [SKILL.md](skills/lizicut/SKILL.md) 并按它执行。内容、文件路径和交付终点说清楚即可，不要求用户自己选择内部阶段。

## 本地安装

将 `skills/lizicut` 整个目录复制到 Codex 的用户技能目录中，例如 Windows 的 `%USERPROFILE%\.codex\skills\lizicut`。保留 `references`、`scripts` 和 `agents`；不要只复制入口文件。重新加载 Skill 后用 `$lizicut` 调用。

可以从上方版本页下载 ZIP，或克隆仓库后复制该目录：

    git clone https://github.com/SalamancaDu/lizicut-skill.git

安装 Skill 不会自动安装 Python、FFmpeg 或外部素材服务；需要合成时先运行下文的 doctor 检查已有工具。

本包自包含，不要求安装其他私人 Skill，不需要原站账户、PostgreSQL、Redis 或任何 API key。语义判断由当前智能体完成。

## 执行能力

- 方法覆盖文稿、解释单元、粗剪保护、画面与模板选择、素材证据、背景、中文排版、动效、音乐、字幕、合成与审片。
- 口播粗剪覆盖重录择优、语义重复、自我纠正、呼吸与跳切取舍。智能体根据实际声音和转录作决定，助手按计划保留/删除，同步视频、原声、字幕与切口位置；不自动判定语义。
- 素材流程覆盖需求检索、候选核验与择优、本地导入/直链下载、文件哈希复用、来源与使用状态记录，以及镜头回填。检索依赖当前可用工具；助手不冒充跨站语义搜索器。
- 自带 Python 标准库助手：环境检查、时间线校验、粗剪字幕重映射、图片/视频主画面、独立透明叠层及淡入淡出、SRT 烧录、音轨 trim/loop/fade/mix/duck、MP4 导出与解码检查。
- 本地合成需要已经安装的 FFmpeg 和 ffprobe；烧录字幕需要其 libass 支持。透明 VP8/VP9 WebM 需分别具有 libvpx / libvpx-vp9 解码器，缺少时会在导出前报告。字体使用本机字体，不随包分发系统字体。
- 搜索、转录、配音、生成素材和复杂动画使用当前环境已有且获授权的工具。缺少这些工具时，Skill 会说明实际缺口；它不捏造已生成素材或已导出视频。
- PR 主流程覆盖文稿/录音确认、项目与序列核对、真实源区间粗剪、素材导入、字幕轨、关键帧、标记、保存和导出前检查；[Premiere 执行](skills/lizicut/references/premiere.md)记录状态回读、中文界面组件名、跨工程防错和 AME 导出边界。
- PS/Illustrator/AE 协作保留分层 PSD、AI、AEP 与实际交接素材；当前本机已实测 Photoshop 与 After Effects 脚本路径，Illustrator 仅定义了可选交接规则，未声称已有专用 MCP。

助手使用说明见 [执行与时间线](skills/lizicut/references/execution.md)。

单独做口播粗剪时读[粗剪规则](skills/lizicut/references/timing-and-roughcut.md)，再使用[执行入口](skills/lizicut/references/execution.md#口播粗剪入口)。已有剪辑工程优先沿用；无指定后端时可直接准备并导出：

    python skills/lizicut/scripts/lizicut.py roughcut roughcut-plan.json --output-dir output/roughcut --render

交付包含源/成片映射、待复核位置和字幕；视频输出可修改时间线与 MP4，音频可输出 WAV。工具仅执行有依据的决定，不凭文字重复或波形低电平自动删原片。

搜索与取得素材时读[素材搜索与落盘](skills/lizicut/references/material-search.md)，智能体用实际检索结果和核验理由准备候选，再执行：

    python skills/lizicut/scripts/lizicut.py materials material-plan.json --output-dir output/materials --download

已有本地文件可省略 --download；--check 仅检查计划。结果 materials.json 保留候选、原页、作者、授权、哈希、实际文件和镜头绑定。未知使用条件或失败项保留为缺口，不伪装成可直接使用的素材；取得文件后仍须合入实际时间线。

## 完整示例与检查

[营收与利润示例](examples/revenue-profit/README.md)提供虚构演示数据、原稿、剪辑决策、字幕、素材和可重建的成片。示例中的数字不对应真实公司，不作为财经事实。

[竖屏分层示例](examples/layered-edit/README.md)复用其中两句真实时长的演示旁白，验证循环背景、独立元素/模板、视频叠层、中文字幕与配乐包络。[v0.1.1 全流程复审](docs/review-v0.1.1.md)记录该版来源、修复与验证边界。

v0.1.2 另有针对粗剪计划的检查，以及带真实音视频流的合成夹具导出：保护/待复核区间保留、替代段不能被删、跨切口字幕拒绝猜测、音视频共用时间与音频 WAV 导出。夹具不是真实主播录制，不能证明自然重录择优或呼吸听感已经通过人工验收。

v0.1.3 的素材检查使用本机 HTTP 夹具与真实图片/视频文件，验证下载、拒绝伪媒体、大小限制、来源保留、重复文件复用和时间线交接；不代表外部素材库、真实性或版权已通过验收。

v0.1.4 修复三处执行问题：保留源文件原有声画偏移和尾部；素材按槽位提交进度，中断后复用已完成文件且残留临时清单不阻塞；下载总超时覆盖慢响应头和慢正文，超时终止工作进程。针对性验证包含非零容器起点、500ms音频延迟、静音区间、视频/音频实际导出、受控中断恢复及本机慢连接；未将这些技术夹具作为真实口播剪辑质量验收。

v0.1.5 是首次公开发布，包含上述功能与修复，补齐 GitHub 下载及安装说明。沿用 v0.1.4 已通过的14项针对性测试结果；本次发布整理未改变剪辑、下载或恢复逻辑。

v0.1.6 修复三处画面合成问题：透明主镜头先与项目背景合成；带 alpha 标记的 VP8/VP9 WebM 显式使用可保留透明度的解码器；主镜头和叠层按含像素比例的显示比例适配，避免非方形像素变形。本版通过5项针对性媒体测试和5项粗剪回归，实际导出并检查透明/半透明像素、图层淡入淡出、contain/cover 尺寸及声画源时钟；也验证了缺少 alpha 解码器会提前失败。测试使用自制夹具，不替代真实成片审阅。

v0.1.7 修复动画入场丢首帧、非整毫秒帧周期无法逐帧编排及字幕预算缺失。时间线增加 duration_frames 与 start_frame/end_frame，兼容既有毫秒字段；粗剪可使用帧边界计算的小数毫秒，音视频与字幕保持同一映射。不可见字幕和显式行数超限会提前报错，自动换行/块高度估算、阅读速度与停留超限会逐条告警，智能体据真实声音与画面修复。本版47项相关检查通过：27项时间线/字幕、14项实际媒体集成、6项粗剪；覆盖24/25/30/60fps、1.160秒入场首帧、分数毫秒源裁切、音效落点、字幕预检及末帧SRT精度。验证范围为本地自制媒体。

v0.2.0 将 PR 设为主执行端，增加文稿/录音确认节点、Premiere MCP 的发现/回读/序列副本/粗剪/素材上轨/字幕/关键帧/标记/保存/导出前检查，以及 PS/Illustrator/AE 可选协作。真实 PR 测试工程已验证 12.96 秒源素材按 `[0,3.6)` 与 `[7.2,12.96)` 重建为 9.36 秒，导入 PS 定版与 AE 透明动效，创建字幕轨、音乐轨和关键帧，实际导出静帧并通过无离线素材/无空隙检查。当前环境缺少可运行的 Adobe Media Encoder，PR 导出任务只能确认已入队，不能把它写成 MP4 成功；见 [v0.2.0 复核](docs/review-v0.2.0.md)。

v0.2.1 根据 AEPS 粗剪评估补齐：时间线间隙默认 0 帧、完整句/段结束才允许 5–8 帧、超过 8 帧失败；同时区分时间线空洞与片段内部静音/黑帧，保护目标工程/序列并处理 MCP 异常回包。字幕增加 `sourceSrtPath/sourceSrtOffset` 源回读约定、无标点字幕的显式样式配置，以及原生字幕轨与最终画面可见性的双层验收。此版本通过 Skill 结构检查、项目检查及既有粗剪/字幕/素材回归；未把新的规则文档更新冒充成一次新的用户 PR 工程实剪验收。

```text
python skills/lizicut/scripts/lizicut.py doctor
python -m unittest discover -s tests -p test_timeline.py -v
python -m unittest discover -s tests -p test_media.py -v
python -m unittest discover -s tests -p test_roughcut.py -v
python -m unittest discover -s tests -p test_materials.py -v
python scripts/check_project.py
```

真实 MP4 导出、解码、可读性与听感各有自己的验证范围。自动检查不能替代人工审片，也不能证明真实新闻、授权素材或付费生成服务可用。

## 来源与许可

规则提取和取舍见 [来源索引](skills/lizicut/references/source-notes.md)。本包不包含旧站配置、凭据、数据库、用户素材及第三方参考视频。

本项目原创文档、脚本和自制示例按 [MIT License](LICENSE) 提供。调用者自己提供或取得的素材继续遵守各自的使用条件。
