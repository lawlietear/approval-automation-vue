# Changelog

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

### 待解决
- [ ] 端到端完整流程测试（连接 Chrome → 提取数据 → 提交 → 完成）
- [x] Tauri 打包发布：Python + Playwright 需要随 exe 分发（pyinstaller 或 resources 方案）
- [x] `tauri.conf.json` `bundle.resources` 配置，确保 config.json 和 Python 代码被打包
- [x] 生产环境路径验证（`resolve_resource` 替代 `current_exe` 回退）
- [ ] CSP 收紧（当前 `null`，开发阶段无影响）

### 已知限制
- `cancel_approval` 中 `cancel\n` 和 `kill()` 几乎同时发生，Python 可能来不及优雅退出（kill 是兜底，不影响功能）
- `find_runner_py` / `find_config_json` 的 exe 路径回退在 prod 模式下需要实地验证
