# v0.2.0 PR 主流程复核

## 范围

本次复核针对 Skill 的新主流程：文稿确认、录音确认、PR 口播粗剪、素材导入、PS/AE 可选协作、PR 动效与字幕、对齐、保存和输出前检查。测试使用本仓库 `examples/premiere-workflow` 的自制夹具，不使用用户原始素材，不改变旧项目。

## 已取得的执行证据

- Premiere Pro MCP 桥接只读检查成功：Premiere Pro 25.6.3，CEP bridge responsive。
- 测试工程 `Lizicut-PR-workflow.prproj` 已打开并回读；目标序列为 `01-Roughcut`，1280×720、25fps、9.36 秒。
- 口播粗剪真实上轨：源 12.96 秒，保留 `[0,3.6)` 与 `[7.2,12.96)`，视频和同期音频均映射到连续的 9.36 秒。
- Photoshop 27.0 生成分层 `design.psd` 及透明 PNG；After Effects 25.2 生成 `motion.aep`，渲染出带 alpha 的 `motion.mov`。
- PR 实际导入源视频、定版图层、AE 动效、音乐、SRT，并创建字幕轨；关键帧使用中文界面组件 `运动/缩放` 成功回读两个值，三个编辑标记成功回读。
- `validate_project_for_export` 在目标工程重新打开后通过：无离线媒体、无时间线空隙、无阻塞错误。
- `export_frame` 成功写出 PR 序列 4.2 秒实际帧并完成静帧检查。

## 未通过或有边界的部分

- `export_sequence` / `add_to_render_queue` 可以返回 queued，但本机 `Adobe Media Encoder 2025` 目录没有可运行程序，启动批量编码后也没有生成 MP4。因此本次不能声称“PR 完成最终视频导出”。
- `get_render_queue_status` 明确返回 AME integration unavailable；后续环境需要安装并连接 AME，或使用另一个已经验证的 PR 编码后端，再补做完整 MP4、ffprobe 和首中尾核查。
- 当前 MCP 在中文 Premiere 中需要实际回读本地化组件名；英文 `Motion/Scale` 和音量参数没有直接成功。关键帧已用本地化名称成功，音乐自动化保留为待补验证项。
- `read_sequence_captions` 受 Premiere DOM 限制不能读回现有字幕文本；字幕源 SRT、创建返回值和实际帧/导出文件必须联合验证。
- Photoshop 与 AE 已实测；本机没有 Illustrator 专用 MCP，因此 Illustrator 分支只完成规则与交接说明。

这些边界保留在 Skill 中，避免把桥接连通、队列入队、结构回读或单帧导出夸大成完整成片验收。
