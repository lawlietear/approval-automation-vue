# 本地待办工具

2026-09-26：本机 Settings/workflow.json 的安全调试开启时，命令 approve 与旧 --test-mode 被拒绝；list/view/status 仍是独立只读入口。正式核心审批复用设置中的部门ID并在当前窗口重验。调试使用说明及当前构建哈希见 SAFE_DEBUG_HANDOVER.md。

供在单位电脑上运行的 Codex 或 PowerShell 使用，无需 MCP，不增加前端按钮。先在 Chrome 登录核心系统并打开有“流程待办”的首页。沿用已有调试模式；默认连接 localhost:9222，其他调试地址使用 -Cdp 指定。本工具不启动浏览器，不绕过登录或单位网络权限。

在绿色版目录运行：

```powershell
./ReadProjects.ps1 -Action list
./ReadProjects.ps1 -Action view -TaskId '从列表返回的编号'
./ReadProjects.ps1 -Action close -TaskId '当前打开的详情任务编号'
./ReadProjects.ps1 -Action unlock
```

返回 JSON Lines：`pending_list` 是待办清单，`project_view` 是提取结果，`task_closed` 表示详情子页已关闭，`session_unlocked` 表示锁屏弹窗已消失，`error` 表示失败。view/close 必须明确使用 task_id，不可使用同名标题代替编号。list/view/close/unlock 不会调用审批及登记；禁止为了读取项目调用旧 runner 审批入口或 --test-mode，旧核心系统测试模式仍可能点击审批弹窗。

unlock 会在本机 PowerShell 中隐藏输入密码；不要把密码写进命令参数、配置或聊天记录。供自动调用的 `-PasswordFromStdin` 仅从重定向的标准输入读取一行 UTF-8 密码，不在终端显示或保存。命令只匹配核心系统 `/amcs/index.htm` 上唯一可见的“当前会话已经失效,屏幕已锁定,请激活!”弹窗，并且只点击该弹窗的“确定”一次。密码过期、扫码登录、普通登录页、其他弹窗或多个锁屏页面均不会被处理。解锁结果只证明前端弹窗消失；若列表仍不可用，请在浏览器中人工检查。

配置优先读取本机 AppData/Local/com.yourcompany.approvaltool/Settings/config.json；不存在时读取绿色版随附 config.json。可通过 -Config 指定。不会写入或迁移配置。

其他参数：-PageUrl 指定完整首页地址以消除多首页歧义；-System old/new 选择核心/OA详情提取规则，默认 old。当前列表适配器仅支持已提供的 TrustUI“流程待办”组件，不代表支持另一套 OA 待办列表。

安全和限制：

- list 只遍历 `trust_pagelet_lcdb` 内已验证的分页控件，逐页读取并校验任务编号；读取后回到第 1 页。`complete=true` 表示读取数量与系统总数一致；若总数缺失，则要求已到达分页末页。分页页码不能推进或状态不一致时会停止并报错。
- view 从第 1 页开始按唯一 task_id 搜索所有分页，再使用原生待办行入口打开匹配事项；同名任务不合并，不猜测项目。
- close 仅关闭核心系统当前激活、编号及详情地址均与 task_id 匹配的内部“待办事宜处理”标签；不会关闭浏览器窗口或其他任务标签。找不到唯一匹配时返回错误。
- 支持同页内部 iframe 和新窗口；委托身份不自动选择，详情任务身份无法验证时停止。
- 只复用既有字段提取规则，不读取附件全文。空标题视为提取失败。摘要必须区分字段事实与推断，不能从标题编造项目概况。
- 打开详情可能产生已读或访问记录。运行期间不要手动切换同一页面，也不要同时在前端发起审批。
- 核心系统新增 approve/status 命令：view 返回15分钟有效的 review_token；用户确认后用 approve + TaskId + ReviewToken + ConfirmTaskId 独立审批。持久化尝试记录禁止重复审批，结果不明时只查 status。仅支持核心首页内部详情标签，不支持 OA 命令审批。详见 VERIFICATION_HANDOVER.md；现有前端审批入口不变。
- 命令结果直接输出给调用方，不经过前端日志保存链路。不要将业务输出上传到公开仓库；交给模型前应符合单位数据要求。

列表分页与详情打开已在真实核心系统页面确认。关闭操作基于已确认的内部标签结构；新版 close 命令尚未在真实页面执行。其他详情结构、委托弹窗和打开行为仍需按具体流程核对。

2026-09-25 代码审查：翻页改为等待非空且任务编号已变化的数据，不再依赖行缓存标识变化；空页或无法确认翻页完成时停止，不猜测读取成功。详情身份检查覆盖全部外层框架，隐藏关闭控件拒绝操作。35项完整回归及补充后的14项待办定向测试通过；`dist_green` 的 list/view/close 已在隔离模拟页面通过打包入口验证，未操作真实审批。其他历史分发目录本轮未更新。
