# Changelog

## 2026-09-26 - 本地版本归档

- 将近期浏览器连接、设置分离、更新框架、本地核心审批命令、界面调整及安全调试审查修复整理为本地Git提交；不推送远端。
- 排除含真实凭据的本机config.json、未使用Notion模块、同步冲突副本及原始采集报告；保留回归测试所需的脱敏部门DOM。提交前新增内容凭据模式扫描及代码空白检查通过；原始DOM保留采集格式。

## 2026-09-26 - 健壮性与功能性审查修复

- 已重打包并更新dist_green主程序/执行组件，核对二进制及关键随包源码一致、两份原配置未变；SAFE_DEBUG_HANDOVER.md记录新哈希。未提交Git。

- P1：正式部门选择后至最终提交之间，选中状态可能变化；增加最终点击前来源、唯一窗口和当前选中ID检查，最终按钮限定在部门弹窗内。缺少最终确认选择器时抛错，不返回完成给登记流程。
- P2：主页面部门弹窗和详情iframe此前计成两个候选导致调试失败；分别识别并校验同一页面，提取留在详情上下文，部门检查留在弹窗上下文。只读部门扫描不再解析无关审批按钮选择器。
- P2：调试结果含完整项目记录，此前被通用事件日志落盘；沿用提取事件规则，debug_result只转发UI，不重复写入诊断日志。
- P2：已有预览时启动异常会残留加载界面；恢复预览并显示失败原因。approval配置为null/数组时明确返回error，避免未捕获异常。
- 验证：64项Python全量回归通过，新增最终确认缺失用例后15项调试定向回归通过；13项Rust测试、前端构建、隔离UI测试和新打包执行组件测试通过。仅使用模拟页面，未执行真实审批或登记。

## 2026-09-26 - 安全调试与部门设置

- 基于已交接的真实部门DOM增加独立安全调试：用户确认步骤数后，仅提取和trial检查，所有真实点击均禁止，不构造登记组件；中间确定可能直提，步骤数不作为放行依据。
- 设置新增“调试与部门”，支持读取已打开窗口、按部门ID保存默认选项及首页显示开关，workflow.json保存在本机Settings。仅完整单页更新缓存，多页明确提示不完整，不自动翻页。
- 正式选择按当前窗口ID和来源重验，校验单选状态后才继续；修复旧页面检测吞掉执行异常并可能重入审批的问题。安全调试时拒绝OA、命令审批和旧test-mode；界面显式调试意图与磁盘设置双重保护。
- 60项Python回归、13项Rust测试、前端构建及模拟界面测试通过；打包执行组件验证三种调试路径零点击、单选状态不变、不读取登记配置。新增SAFE_DEBUG_HANDOVER.md，真实单位运行仍待用户验证。
- 已更新dist_green主程序及执行组件，校验构建和关键随包源码一致；2份原配置哈希不变，其他分发目录未更新。构建哈希记录在SAFE_DEBUG_HANDOVER.md。

## 2026-09-26 - 调试模式真实页面采集

- 用户手动打开部门选择窗口后，以 Playwright/CDP 只读采集完整窗口结构、截图和两项单选；`click(trial=True)` 检查目标可点击后仍未选中。
- 读取本次流程最终确定回调，确认该按钮直达审批提交；还发现中间确认仅在部门列表满足条件时进入选择窗口，否则可直接提交。整理 `DEBUG_MODE_CAPTURE_HANDOVER_2026-09-26.md` 及 `captures/` 交接材料。没有点击审批、选项或最终确定，没有登记，也没有修改程序。
- 用户重新停在中间确认弹窗后，补采 `#h_msg_floatdiv` 与遮罩 `#h_msg_bg` 的完整 DOM、局部截图和 `#buttonOK` 的绑定回调；没有点击确定或取消。其他流程的一步提交情况尚未采集；本次结果仅适用于已观察的经营性费用支付审批流程。

## 2026-09-25 - 默认紧凑窗口

- 默认窗口由1000x750调整为1000x640，预览长内容独立纵向滚动；左侧缩减区块间距，并把倒计时合并到预览标题行。
- 前端构建及模拟浏览器验证通过：640高度下左侧含数据切换/倒计时完整显示，右侧独立滚动，展开日志后审批按钮仍可见。

## 2026-09-25 - 紧凑信息预览与操作反馈

- 左右区域调整为52%/48%，右侧减少留白；标题、备注、合同编号完整换行，额外提取字段及数值0不再遗漏，窄窗口改为上下排列。
- 保留并排审批按钮和连接按钮的SVG+文字说明，增加悬停扫光、按下反馈、执行中高亮和本地重复点击保护；减少动画设置继续生效。
- 前端类型检查和生产构建通过；隔离模拟浏览器验证1000/700/390宽度、长文本、额外字段、数值0、执行状态、深色及减少动画模式通过。未连接真实审批系统。
- 设置保存回归及桌面release编译通过，dist_green主程序已更新；原配置与审批命令组件保持不变，其他分发目录未更新。

## 2026-09-25 - 核心系统会话锁屏解锁命令

- 新增 `ReadProjects.ps1 -Action unlock`，本机隐藏输入或重定向标准输入密码；执行组件仅识别唯一、可见的核心系统会话锁屏，点击该弹窗“确定”一次并确认弹窗消失，不审批、不登记，不保存或输出密码。
- 将既有绿色版的点击前字段复核与受保护的单次点击逻辑合回源码，补回同步冲突中的两项安全回归；50项隔离回归通过。新版绿色版在独立 localhost 模拟页面验收解锁、重复拒绝、原 list/view/模拟审批/status 通过；原配置与推送设置哈希不变。真实锁屏解锁动作尚未复现。

## 2026-09-25 - 审批命令隔离验收

- 修正模拟页的空待办容器布局，正式程序未改。当前源码 45 项回归通过；绿色版在独立 localhost 模拟环境完成 list/view/模拟批准/status/重复拒绝，缺少确认编号的命令在启动执行组件前拒绝。
- 真实核心系统会话失效弹窗遮挡分页，未完成只读清单与详情验收，未批准任何真实事项。当前源码、随包源码及同步冲突测试文件存在版本不一致，详见 `VERIFICATION_REPORT_2026-09-25.md`。

## 2026-09-25 - 待办工具审查修复

- 修复分页加载空窗造成漏读、复用缓存行标识导致等待异常；改为等待非空且任务编号变化的数据。异常的可用分页链接不再当作末页。
- 详情身份检查遍历全部祖先框架；关闭命令拒绝 visibility:hidden/collapse 控件；首页恢复失败不再覆盖读取原始错误。
- 新增6项回归测试：完整35项及随后14项待办定向测试通过。重新打包并更新 dist_green 执行组件，隔离模拟页面验证 list/view/close 通过，2份配置哈希不变。真实单位关闭动作未验证，其他分发目录未更新。

## 2026-09-25 - 本地待办翻页与详情关闭入口

- 将核心系统内部详情标签关闭接入 `ReadProjects.ps1 -Action close -TaskId`；仅在当前激活标签的任务编号、详情地址及关闭控件均匹配时关闭，输出 `task_closed`。保留已有的 list 全分页读取及 view 跨页定位，无新增桌面界面。
- 更新本地调用说明并重打包 Python 执行组件和绿色版。构建及文件核对通过；配置文件与推送设置和上一版哈希一致。新版 close 尚未在真实页面执行。

## 2026-09-24 - 本地只读待办工具

- 新增 ReadProjects.ps1 的 list/view 入口，无前端按钮：读取 TrustUI 待办缓存、按任务编号点击原生行、核对详情身份并复用字段提取；不审批、不登记。支持内部 iframe 和新窗口，未知/重复任务、跨源地址、身份选择、空标题失败时停止。
- 新增独立只读提取分支，不能将旧核心系统 test-mode 当成只读；旧审批入口保持兼容。部分列表明确返回 complete=false，不自动处理尚未提供结构的更多/分页页面。
- 30项全套测试通过，随后8项待办定向测试覆盖更严格的字段隔离；实际打包脚本在隔离本机页面端到端验证 list/view 和中文输出通过。真实单位系统仍待只读联调。详见 LOCAL_TOOLS.md。

## 2026-09-24 - 修正工作台视觉层级

- 连接、检测、专用浏览器使用 SVG 加可见文字，不依赖悬停识别含义；保持连接区域紧凑。
- 审批恢复左右并排的常规尺寸按钮，通过缩短前置区域上移位置；数量改为1至10下拉选择，默认1。

## 2026-09-24 - 突出审批主操作

- 连接区域改为轻量状态栏，检测与启动专用浏览器采用带提示和无障碍名称的图标；连接异常、等待及未保存提示仍完整显示。
- 数量改为单个输入框，与业务类型并排；核心业务与 OA 审批改为纵向大按钮。流程条、登记状态减轻视觉权重，非运行状态隐藏取消入口。审批及登记逻辑不变。

## 2026-09-24 - 本地五天运行日志

- 按本机日期在独立 Logs 目录追加保存界面日志、审批事件及执行组件 stderr；保留今天及前四天，启动及写入时清理更早的本程序日志文件。
- 底部新增打开日志目录入口。记录时间、进程、来源和消息；不保存完整提取数据事件，链接及常见凭据脱敏，写入失败提示用户，不自动上传。

## 2026-09-24 - 企业微信失败诊断

- 将 HTTP 状态、业务错误码及脱敏提示传入登记日志，区分代理、证书、超时及网络连接失败；不打印完整 Webhook 或凭据，不自动重试。
- 不再将非 JSON 或缺失成功码的响应视作成功，过滤空字段标识；部分通道失败时明确已成功通道不受影响，避免重跑审批。新增 5 项模拟错误回归，全部 23 项 Python 测试通过。

## 2.1.0 - 工作台、独立本机配置与绿色版联网更新

- 工作台只展示连接、审批参数、登记状态和审批操作；顶部设置入口统一管理数据登记、浏览器和软件更新。默认自动识别优先保留 localhost:9222，保留 IPv4 / IPv6 修复。
- 配置首次从旧版迁移到本机 AppData/Local/com.yourcompany.approvaltool/Settings；后续更新不覆盖。浏览器偏好也迁入文件，兼容旧 localStorage；开发模式独立 Settings-dev。不新增配置备份/导出功能。
- 绿色版联网更新框架：HTTPS 版本信息、Tauri 签名验证下载、程序文件白名单解压、退出后替换与失败恢复；审批期间禁止安装更新。未设置发布地址与公钥时明确显示未配置。
- 增加发布脚本 scripts/package-update.py 和 ONLINE_UPDATES.md。发布源可放国内对象存储，不依赖 GitHub；当前尚未配置真实更新源，因此没有完成线上升级联调。

## 2026-09-24 - 恢复 localhost 连接兼容性

- 修复固定访问 127.0.0.1 导致原有 localhost:9222 可用却无法直接连接的问题。端口检测和动态发现恢复 localhost 解析，支持 IPv4 / IPv6 本机监听，保留服务返回的 WebSocket 地址。
- 本机地址校验增加 [::1]，仍拒绝外部地址。新增 IPv4-only / IPv6-only 服务的 HTTP 发现到 WebSocket 验证回归测试。
- 不修改快捷方式、ChromeDebug 资料或用户登记配置；本次不合并设置界面重构。

## 2026-09-24 - 多种浏览器连接方式

- 分离检测状态、直接连接、启动专用浏览器。检测和直接连接均不启动窗口；直接连接以 Browser.getVersion 实际验证 CDP，不以端口开放判断连接成功。
- 支持从 Chrome 资料根目录的 DevToolsActivePort 发现新版授权调试动态地址，保留手动端口连接；开始审批使用本次验证的真实 WebSocket 地址。
- 界面可调整端口、Chrome 程序路径、自动发现资料根目录，自动保存本机设置。更改设置清除已连接状态；专用资料按端口隔离，默认端口继续使用已有 ChromeProfile。
- 新版授权提示由用户确认，不能绕过；正式审批新建连接可能再次请求授权。检测发现不等于授权成功。

## 2026-09-24 - 一键启动审批浏览器

- 连接入口自动复用本机调试 Chrome；未启动时使用独立 ChromeProfile 自动打开浏览器，无需用户修改快捷方式。
- 限定本机端口并验证 CDP 信息；超时、端口被无关程序占用、未找到 Chrome 时显示说明。启动时禁止重复点击和开始审批。
- 登录资料仅保存在本机应用数据目录，不修改普通 Chrome，不复制密码，不绕过企业策略；首次需在专用窗口登录。

## 2026-09-24 - 企业微信 schema 导入修复

- 识别完整请求中字段 ID 对应的 title/type/enum 对象，兼容单独 schema、简写映射和旧 webhook.schema；忽略示例记录，不发送数据。
- 支持金额/合同金额、日期/时间等别名，处理 Markdown 代码块、转义下划线和末尾空格实体。
- 识别失败或字段歧义时保留原映射；部分成功明确列出留空字段。新增 6 项解析回归测试：Node 24 下运行 `node tests/wechat-schema.test.mjs`。

## 2026-09-23 - 流程弹窗等待优化

- 核心系统点击链取消固定等待，按钮出现且可操作后立即继续；主页面与 iframe 共用 5 秒查找期限。
- 部门精确匹配，最终确认绑定选中部门的页面上下文；不强制点击隐藏、遮挡或多个同名目标。配置的步骤超时即停止后续点击和登记。
- 新增 7 项本地 Edge 无头浏览器测试，覆盖延迟弹窗、隐藏副本、遮挡、重复目标、超时、测试模式取消及完整点击顺序。未进行真实 OA 审批联调。

## 2026-09-22 - 登记设置与 Obsidian 台账

- 企业微信支持独立开关、Webhook 链接、字段映射及超时的可视化编辑；设置仅保存在本机。
- Obsidian 支持独立开关与目录选择，按日期和当日最大序号续写，独占创建避免并发覆盖。
- 对齐既有台账的日期、项目名称、金额字段，不写入额外时间属性；旧记录不自动迁移。
- 两个登记通道独立执行，正确报告部分失败；不调用 Notion，也不自动回退腾讯表单。
- 优化中文界面、明暗对比及设置入口；开发模式优先使用 Python 源码。
- 纳入登记测试和 PyInstaller 打包配置。个人 config.json 修改、push-settings.json、旧 Notion 模块和发布产物不纳入本次提交。
- 工作区上级目录的开发及分享脚本不属于此 Git 仓库，此提交不包含这些文件。

## v2.0.0 — Tauri 迁移（进行中）

### 已完成

#### 2026-05-08 — 前端 UI/UX Phase 1
- Vue 3 + Vite + TypeScript 重构完成，替换原有 PyQt5 GUI
- 橙色主题 + glassmorphism 设计系统（CSS 变量 `:root` + `data-theme="light"`）
- 点阵网格背景动画（`dot-grid-bg`）
- 磁吸按钮效果（`useMagnetic` composable）
- 四步流程指示器（conn → pull → submit → done），带充电动画
- 状态卡片、参数卡片、操作卡片玻璃态面板
- 日志抽屉（LogDrawer），自动展开错误日志，带类型指示灯
- 30 秒倒计时自动隐藏 + 视图切换保留数据

#### 2026-05-08 — 后端集成 Phase 2
- **架构决策**：不复写 Playwright 逻辑，采用 Python 子进程 + JSON Lines stdout 桥接
  - Rust（Tauri）负责任务调度、进程管理、事件转发
  - Python（runner.py）复用原有成熟逻辑，通过 stdout 输出 JSON 事件流
  - `sys.stdout` 重定向到 `sys.stderr`，防止 src/*.py 的 print 污染 JSON Lines
- Rust 命令实现：
  - `connect_chrome`：TCP + HTTP 验证 Chrome CDP 端口
  - `start_approval`：`tokio::process::Command` 启动 `python runner.py`，`BufReader` 逐行解析 stdout，`app.emit()` 转发事件
  - `cancel_approval`：stdin 写入 `"cancel\n"` + `child.kill()` 双保险
  - `get_config`：读取 config.json 返回完整配置对象
- 前端事件监听：`approval:log`, `approval:data_extracted`, `approval:submit_success`, `approval:all_done`, `approval:error`, `approval:finished`
- 子进程生命周期管理：`tokio::sync::Mutex` 存储 `Child` + `cancel_tx`，防止重复启动，自动清理已结束进程

#### 2026-05-08 — Tauri v2 兼容修复
- **capabilities 配置**：创建 `src-tauri/capabilities/default.json`，显式授权 `core:event:allow-listen`, `core:event:allow-emit`, `core:event:allow-unlisten`
- **参数映射修复**：Tauri v2 中结构体参数需要前端用参数名包裹（`{ payload: {...} }`），而基本类型直接扁平映射。将所有命令参数统一为扁平形式，避免前端传参歧义
  - `start_approval`：`StartPayload` 结构体 → 6 个独立 `String`/`bool` 参数
  - `get_config`：`GetConfigPayload` 结构体 → `config_path: String`
- **路径探测**：`find_runner_py()` / `find_config_json()` 多候选路径回退，覆盖 dev（`cargo run`）和 prod（exe）模式

#### 2026-05-08 — 动态配置加载
- `LeftPanel.vue` 业务类型下拉框从硬编码 14 项改为从 `config.json` 动态读取 `approval.biz_type_options`
- 新增 `get_config` Rust 命令，前端 `onMounted` 时加载，日志面板显示加载结果

#### 2026-05-08 — Tauri 打包与发布
- **PyInstaller 打包 Python 运行时**：复用原项目 `gui_run.spec` 经验，新建 `runner.spec` 将 `runner.py` 及 Playwright 驱动打包为 `ApprovalRunner.exe`（onedir 模式）
- **`bundle.resources` 嵌入**：`tauri.conf.json` 配置 `"resources": ["python/dist/ApprovalRunner"]`，将 Python 运行时完整目录打包进安装包
- **生产环境路径探测**：Rust `find_runner_py` / `find_config_json` 新增 `app.path().resolve(..., BaseDirectory::Resource)` 优先分支，prod 模式下自动定位捆绑资源，dev 模式保持原有文件系统探测不变
- **命令构建适配**：`start_approval` 根据 runner 路径扩展名（`.exe` vs `.py`）自动选择直接调用 exe 或 `python runner.py`
- **安装包输出**：MSI (54MB) + NSIS (38MB)，可在无 Python 环境的 Windows 机器上直接安装运行

### 技术栈选型

#### 1. 桌面端套壳方案：为什么选 Tauri 而非 Electron / PyQt5 / Wails

本项目本质是一个**浏览器自动化工具**（操作 Chrome）+ **数据上报工具**（Webhook/腾讯文档），核心逻辑在 Python 侧，桌面端只需要一个轻量壳来承载 UI 和调度。可选方案对比：

| 方案 | 前端技术 | 后端/壳语言 | 打包体积 | 内存占用 | 在本项目中的优劣 |
|------|---------|-----------|---------|---------|----------------|
| **Electron** | Chromium + Node.js | Node.js | ~150MB+ | 高（独立 Chromium） | 生态最成熟，但为本项目严重 overkill。用户 already 需要 Chrome 跑自动化，再内嵌一个 Chromium 是双重浪费；体积和启动速度也是硬伤。 |
| **Tauri** | WebView2 (Edge) | Rust | ~3-5MB | 低（共享系统 WebView2） | **选中**。体积极小，启动快；Rust 侧做进程调度、文件 IO、网络验证非常合适；Windows 11 自带 WebView2，无需额外安装。 |
| **Wails** | WebView2 | Go | ~10MB+ | 低 | 和 Tauri 类似，但 Go 在桌面端生态略逊于 Rust（Tauri v2 的权限系统、插件生态更成熟）。 |
| **PyQt5（原有方案）** | QWidget | Python | ~60MB+ (PyInstaller) | 中 | 原有 v1 方案。PyQt5 的 GUI 开发效率低，现代化 UI（动画、响应式布局、主题切换）实现成本极高；且 Qt 的线程模型和 Playwright 的 greenlet 有冲突历史。 |
| **Flutter Desktop** | Flutter Engine | Dart | ~20MB+ | 中 | 跨平台能力强，但 WebView/浏览器自动化集成不友好；生态重心在移动端，桌面端第三方库支持弱。 |

**决策**：Tauri。理由：（1）用户机器 already 有 Chrome 和 Edge WebView2，不需要再打包一个浏览器内核；（2）Rust 的异步运行时（tokio）做子进程管理、stdout 读取、事件转发非常自然；（3）前端可以用现代 Web 技术（CSS 动画、响应式布局），UI 迭代速度远超 PyQt5。

#### 2. 前端框架：为什么选 Vue 3 而非 React / Svelte

| 框架 | 在本项目中的优劣 |
|------|----------------|
| **Vue 3** | **选中**。组合式 API (`<script setup>`) 和 TypeScript 集成非常顺滑；模板语法对后端/运维出身的开发者更友好（更接近 HTML）；`v-model` 双向绑定减少样板代码；Vite 冷启动和热更新极快。 |
| **React** | 生态最大，但 JSX 的灵活性对本项目反而是负担（不需要复杂状态管理，不需要庞大组件库）；useEffect 心智负担比 Vue 的 watch/computed 重。 |
| **Svelte** | 编译时优化，运行时极小，但生态成熟度（尤其是和 Tauri 的集成文档、类型定义）不如 Vue。 |

**决策**：Vue 3 + Vite + TypeScript。理由：（1）项目 UI 复杂度中等（表单、按钮、日志列表、步骤条），Vue 的模板语法最契合；（2）Tauri 官方示例和社区资源中 Vue 的配套最完善；（3）TypeScript 提供类型安全，尤其在 Tauri `invoke`/`listen` 的 payload 类型上能提前 catch 错误。

#### 3. 各技术在本项目中的具体职责

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户桌面窗口                             │
│  ┌──────────────┐  ┌─────────────────────────────────────────┐  │
│  │ Vue 3 (Web)  │  │  Rust (Tauri)                           │  │
│  │              │  │  • 进程调度：启动/停止 Python 子进程      │  │
│  │ • 响应式 UI  │◄─┼─• 事件转发：stdout JSON → Tauri Event   │  │
│  │ • 主题/动画  │  │  • 路径探测：dev/prod 双模式找 runner.py  │  │
│  │ • 表单绑定   │  │  • 配置读取：get_config → 前端动态下拉框   │  │
│  │ • 日志面板   │  │  • Chrome 验证：TCP + HTTP 探活           │  │
│  └──────────────┘  └─────────────────────────────────────────┘  │
│         ▲                          │                            │
│         │ invoke / listen          │ tokio::process::Command    │
│         └──────────────────────────┘                            │
│                              ┌──────────────────────────────┐  │
│                              │ Python (Playwright)          │  │
│                              │ • CDP 连接 Chrome            │  │
│                              │ • iframe 遍历/字段提取       │  │
│                              │ • JSON Lines stdout 输出      │  │
│                              │ • stdin 监听取消信号         │  │
│                              └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

- **Vue 3**：负责所有用户可见的界面（左侧面板、右侧数据展示、日志抽屉）。通过 `@tauri-apps/api` 的 `invoke` 调用 Rust 命令、`listen` 接收实时事件。
- **TypeScript**：在前端提供 `invoke` payload 的类型约束、事件回调的 `payload` 类型推断、组件 props 的编译时检查。没有 TS，Tauri 的前后端接口很容易因字段名/类型不一致而出错。
- **Rust / Tauri**：桌面壳 + 系统层胶水。不做业务逻辑，只做三件事：（1）启动 Python 子进程并喂参数；（2）读取 Python stdout 的 JSON Lines，通过 Tauri Event 推给前端；（3）管理子进程生命周期（防重复启动、取消、清理）。
- **Python / Playwright**：保留原有 v1 的完整业务逻辑。runner.py 是一个薄包装层，把原来的 `run.py` 改造为命令行入口 + JSON Lines 输出，核心 `src/*.py` 零改动。
- **Vite**：前端构建工具。开发时提供 HMR（热模块替换），生产时打包为静态文件供 Tauri 嵌入。
- **WebView2 (Edge)**：Windows 系统级浏览器组件，Tauri 用它来渲染 Vue 前端。用户无需额外安装，Windows 11 自带。

### 关键决策
1. **不复写 Playwright 逻辑**：原有 Python 代码 2000+ 行，涉及 CDP 连接、iframe 递归遍历、合同字段智能提取、多 selector fallback、Old/New OA 双系统适配。Rust 生态无成熟替代方案，重写风险高、工期长。
2. **JSON Lines 而非 IPC/HTTP**：stdout 逐行输出 JSON 是最简单的跨语言通信方式，无需额外端口、协议或序列化库。
3. **stdin 取消而非信号**：Windows 下 Python 信号处理不一致，通过 stdin 写入 `"cancel\n"` 更可靠。
4. **扁平参数优先于结构体**：Tauri v2 的参数反序列化规则中，结构体参数需要前端用参数名包裹，而基本类型直接扁平映射。为保持前后端一致性，所有命令采用扁平参数。

#### 2026-05-12 — 页面匹配与数据校验
- **OA 系统页面匹配修复**：`runner.py` 中 New OA 的 `url_hint` 改为 `["10.0.0.1", "collaboration"]` 双条件 AND 匹配，避免匹配到 OA 首页而非审批详情页
  - `browser.py` `get_approval_page()` 支持 `url_hint` 传入字符串或字符串列表，列表时要求所有 hint 同时满足
  - `page_hint` 修正为 `"鲁信集团OA内网门户"`
- **数据提交前校验**：`runner.py` 在提交前检查关键字段（`事项名称`、`部门`、`工作类型`），若全部为空则停止提交并输出错误日志，防止提交空数据

#### 2026-05-12 — 绿色版打包脚本
- 新增 `build-green.py`（Python 脚本替代 `.bat`），解决 Windows CMD 对 UTF-8 无 BOM 批处理文件的编码解析问题
  - 自动检测 `npm` / `cargo` 路径（`shutil.which()`），无需用户手动配置环境变量
  - 一键执行：环境检查 → PyInstaller → `npm run build` → `cargo build --release` → 资源复制 → 验证输出
  - 输出目录：`dist_green/ApprovalTool.exe` + `python/dist/ApprovalRunner/`

#### 2026-05-12 — 启动白屏修复
- **根因定位**：`style.css` 中存在 `@import url('https://fonts.googleapis.com/...')`，打包后的 CSS 在 WebView2 中加载时会阻塞渲染，等待网络请求（2-3 秒），导致启动白屏
  - ✅ **已删除** `style.css` 中的 Google Fonts `@import`
- **加载动画**：`index.html` 内联纯 CSS loading 动画（脉冲光晕 + 三层反向旋转圆环 + 中心发光点 + 渐变文字），不依赖任何外部资源或 JS
- **最小显示时间**：`App.vue` `onMounted` 中强制 loader 至少显示 1.2 秒后再淡出，避免 JS 加载过快导致动画一闪而过
- **窗口背景兜底**：`tauri.conf.json` 新增 `"backgroundColor": "#0f0f0f"`，确保 WebView2 初始化完成前窗口背景为深色而非白色

### 待解决
- [ ] 端到端完整流程测试（连接 Chrome → 提取数据 → 提交 → 完成）
- [x] Tauri 打包发布：Python + Playwright 需要随 exe 分发（pyinstaller 或 resources 方案）
- [x] `tauri.conf.json` `bundle.resources` 配置，确保 config.json 和 Python 代码被打包
- [x] 生产环境路径验证（`resolve_resource` 替代 `current_exe` 回退）
- [ ] CSP 收紧（当前 `null`，开发阶段无影响）

### 已知限制
- `cancel_approval` 中 `cancel\n` 和 `kill()` 几乎同时发生，Python 可能来不及优雅退出（kill 是兜底，不影响功能）
- `find_runner_py` / `find_config_json` 的 exe 路径回退在 prod 模式下需要实地验证
