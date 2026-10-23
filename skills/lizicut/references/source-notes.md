# 提取来源与取舍

本包提取自 SalamancaDu 的 lizicut.com / SnapFilm，审阅代码基线为 `06c43b66e08f0dbf5df56eddbf66c7aae1dc5208`（2026-05-07）。源仓库目前为私有；本包不需要访问源仓库、旧站数据库或服务。

同时参考用户提供的 `模板分类0117.xmind`、`影片制作 v2.xmind`、`制作预设背景.xmind`，以及本地项目中的财经科普风格稿。原文件未复制进开源包。

## 规则提取索引

下列路径相对于原项目。表中的“改写”是本包设计取舍，不冒充旧系统已具备的行为。

| 来源 | 提取内容 | 本包处理 |
|---|---|---|
| 模板分类0117.xmind | 信息效率优先；11 类表达；双语语义检索与提示词；字幕与模板文字分工；按段落配乐 | 先判断目的再选载体；数字/地名/“他说”不自动触发模板；精确文字可控排版；删去纯画面总时长硬配额；旧供应商名称不变成 Skill 依赖 |
| 影片制作 v2.xmind | 文稿—录音—粗剪—三模块预分配—素材—动效—声音—对齐—可编辑交付/导出 | 背景、元素、模板分别选择；独立入场、按任务交接；抠图/身份遮罩按用途选；可选首帧转视频；来源和实际文件落到同一时间线；辅助合成器增加独立叠层 |
| 制作预设背景.xmind | 主题图可选、情绪纹理/理性网格、降饱和、深浅渐变、暗角、阅读优先 | 保留两类背景倾向及循环检查；纹理和 80%—90% 透明度改为可调配方；压暗在背景层完成 |
| packages/shared/src/lib/snapfilm/classifier.ts | 载体与模板正交、叙事角色、语义意图 | 保留；不携带旧站分类器和二次模型调用 |
| packages/shared/src/lib/snapfilm/planning-template-intent.ts | 11 类信息表达线索 | 提取为语义判断及反例；“他说→波形”等关键词规则不直接照搬 |
| packages/shared/src/lib/snapfilm/text-splitter.ts | 标点辅助定位、处理小数点 | 字幕定位可用；镜头单位改按解释任务组织 |
| packages/shared/src/lib/snapfilm/video-pacing.ts | 2—5 秒画面、5—10 秒模板、15 秒连续画面、10—30 秒预算 | 前几项只作观察值；不照搬长片固定预算 |
| packages/shared/src/lib/snapfilm/host-roughcut/roughcut-cut-profile-v1.ts | 不同强度的句头句尾保护、最短片段 | 列明原始参考量与适用前提，不声称复刻 ASR 算法 |
| packages/shared/src/lib/snapfilm/host-roughcut/roughcut-rhythm-tier-policy-v1.ts | 共享停顿语义、按强度改变安全停顿删减预算 | 保留原则；不追求固定删减率 |
| packages/shared/src/lib/snapfilm/host-roughcut/caption-timing-confidence-v1.ts | 低置信度降级，不把缺值视作高置信度 | 保留；辅助工具对跨切口字幕报出具体缺口 |
| packages/shared/src/lib/snapfilm/host-roughcut/asr-transcript-repair-v1.ts | 重复串句/错挂尾巴修复，仅从已有 words 选择连续区间，不新增词 | 明确区分“修转写”与“剪原片”；重复提示不能当作真实重录或语义重复的删除证据 |
| packages/shared/src/lib/snapfilm/host-roughcut/roughcut-filler-lexicon-v1.ts | 词元候选与整单元 filler 判断分开 | 词表只提示，补上指示词、强调、步骤连接词的保留条件 |
| packages/shared/src/lib/snapfilm/host-roughcut/roughcut-safe-pause-eligibility-v1.ts | 字幕敏感、语义、慢节奏、修复敏感与外部保护先于停顿压缩 | 保留分类/保护思路；正常呼吸与弱读不按低电平直接删除 |
| packages/shared/src/lib/snapfilm/host-roughcut/roughcut-semantic-unit-cut-protection-v1.ts | 小幅恢复误切的完整语义单元，统计部分单元违规 | 提炼为完整短语、论证与保护区间；不照搬恢复比例或把低覆盖单元一律删除 |
| packages/shared/src/lib/snapfilm/sequence-continuity/playbook-v1.ts | 进入、桥接、收束/独立；来源与锚点沿用、更新、重建 | 保留为编辑判断，跨板有共同锚点，不能沿用无关来源身份；不携带原运行时元数据系统 |
| packages/shared/src/lib/snapfilm/material-authority/board-material-contract-v1.ts | 证据板真实性优先、生成素材仅辅助 | 保留；时间线禁止把生成素材标为事实证据 |
| packages/shared/src/lib/snapfilm/search/search-contract.ts、search-provider-registry.ts、image-source-policy.ts | 图片/视频能力分开、可用来源与导入能力分别判断 | 改为检查当前智能体工具；旧供应商注册不变成开源 Skill 依赖 |
| packages/shared/src/lib/snapfilm/internal-generation/search-runtime-v1.ts | 规范/去重查询、按原图 URL 去重、多源交错与失败信息 | 保留有理由的查询调整、多源候选比较与去重；不照搬固定排序/配额，不把轮询顺序说成语义评分 |
| packages/shared/src/lib/snapfilm/image-search/types.ts、image-search/import.ts、video-search/types.ts、video-search/import.ts | 原页/原媒体/预览分离，来源/作者/许可/署名，限时限量下载与正式导入 | 改为本地落盘、哈希复用、媒体检查与可移植来源记录，不携带 OSS、数据库或内容审核供应商 |
| packages/shared/src/lib/snapfilm/prompt/prompt-builder.ts | 区分搜索词与提示词、空间留白、风格一致性 | 保留意图；不照搬关键词切片或旧模型参数 |
| packages/shared/src/lib/snapfilm/role-motion-preference-v1.ts | 动效随叙事角色而变 | 保留目的；不把漂浮、扫光等设为每镜常驻动作 |
| packages/shared/src/lib/snapfilm/audio-planner-v1.ts | 统一音轨、trim、loop、gain、fade 与 ducking | 转成可移植时间线；新助手扩展原声保护、平滑包络与短间隙保持，参数不冒充原实现 |
| packages/shared/src/lib/snapfilm/export/snapfilm-export-timeline-plan-v1.ts | 单一时间线、顺序与时长校验、预览/导出一致 | 提取为简单显式合同，不迁移旧站对象模型 |
| docs/瞬影/02_系统与实现/瞬影数据集/2026-04-03-财经科普主风格定义稿-v0.md | 前快后稳、强/中/弱主持、解释责任锚点、可读证据板、单板聚焦、克制电影化 | 财经默认考虑中等出现档；无真人时由稳定锚点接责，不强制代理角色；题材空间可变而解释骨架连续；本地资料未确认全部进入 Git 历史 |

## 有意不携带的部分

登录、会员、支付、积分、素材交易、管理后台、队列服务、生产发布、训练样本经营、旧数据库访问与模型供应商集成不属于本包。与网站身份相关的 Logo、用户内容、系统字体及第三方参考视频没有复制。

分类 system prompt、模板记录和部分动效参数可由原项目的 `settings.ts`、`system-prompt-repository.ts`、`template-repository.ts` 从数据库覆盖。本包只提取已读源码、导图及本地文档能确认的方法；未连接原业务库，不声称还原旧站最后一次实际配置。

本包的时间线助手是新写的独立实现，未逐文件迁移原应用代码。它验证时间和技术连通，不提供原系统的 ASR、自动配图或审美评分能力。

v0.1.2 专门补强口播粗剪。在上述 host-roughcut 规则中确认了转写修复、语义单元保护、停顿分类与孤立口癖；没有把这些源码说成已经实现了通用重录择优或跳切修复。新增的择优顺序、语义重复/纠正反例、呼吸接缝处理、跳切取舍及 roughcut 计划编译器，是本包在原原则上的补充。语义判断仍由当前智能体依据实际声音和上下文完成；新助手不伪装成 ASR、自然呼吸检测器或语义质量评估器。

v0.1.3 补强素材检索链路，按上述 search/runtime/import 源码确认候选、预览、原文件与正式导入的区别，并保留出处/作者/许可字段。需求驱动的择优次序、unknown 使用状态保留、内容哈希去重、同计划复用和本地 materials 助手是本包新增实现。未移植供应商 API 或旧云存储；实际检索/核验仍由智能体及其当前可用工具完成，脚本不提供审美、法律或事实自动认证。

v0.1.4 修正本包执行器的三处问题：按共同源时钟保留音视频起始偏移并校验结束位置；素材取得前及每槽位后提交检查点、恢复同计划已完成文件；HTTP(S)取得由可终止的独立进程执行总超时。对应验证使用有延迟与非零容器起点的合成音视频、受控中断/残留清单和本机慢响应夹具，不冒充真实口播听感或外部素材库验收。

v0.1.1 复审时还核对了 `audio-branch.ts`（无录音不强制生成）、`image-source-policy.ts`（可配置来源/导入能力）、`template-subtitle-policy-surface-v1.ts`（字幕安全区和预览/导出职责）、`default-motion-strategy-v1.ts`（按场景委托动作规划）。本包保留输入分支、真实能力检查、字幕独立与动作职责，不迁移供应商、数据库开关和模板编辑器协议。
