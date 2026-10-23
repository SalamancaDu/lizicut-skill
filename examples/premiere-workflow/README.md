# Premiere 主流程夹具

这是用于验证 Skill 的自制小型夹具，不是用户素材，也不是可直接发布的成片。运行 `scripts/make_premiere_fixture.py` 会生成源视频、音乐、字幕和一个用于 PR 导入的素材目录；生成的媒体、`.prproj`、Adobe 自动保存目录和输出文件默认被 `.gitignore` 排除。

两个 JSX 文件分别演示 Photoshop 分层定版和 After Effects 透明动效的可编辑交接。真实制作时先确认当前应用和未保存工作，再按 [Adobe 协作](../../skills/lizicut/references/adobe-collaboration.md)执行。Illustrator 没有在本机验证专用连接，因此只遵循同一套可编辑源与交接记录规则。

验证时的 PR 序列使用 1280×720、25fps：

- 源素材保留 `[0, 3.6)` 和 `[7.2, 12.96)`，以 `add_to_timeline_batch` 进入序列，成片时长为 9.36 秒。
- 透明 AE 动效、PS 定版、两段字幕图层、音乐和 SRT 字幕轨分别进入独立轨道。
- PR 回读了源入/出点、序列区间、轨道、标记和关键帧；`validate_project_for_export` 报告无离线媒体和无时间线空隙。
- `export_frame` 已输出实际 PR 帧。完整 MP4 还需要可运行的 Adobe Media Encoder；“已入队”不作为导出完成证据。
