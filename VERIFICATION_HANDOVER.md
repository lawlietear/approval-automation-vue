# 核心业务系统：两步审批验证交接

本次构建：2026-09-25；ApprovalRunner.exe SHA256 为 `2D522AF1F263FEE334D7607A0F6713FCA1BA5F2C1DD37A3FC2FCFC29A7DB0BFE`。新增独立 `unlock` 命令，详见 `LOCAL_TOOLS.md`；它只处理已识别的核心系统锁屏，不执行审批或登记。
家里电脑原构建曾通过47项回归及隔离端到端验证（含本地登记）。本机统一源码后通过50项隔离回归；新版绿色版在独立 localhost 模拟环境完成 list/view/模拟批准/status/重复拒绝，以及 unlock 单次解锁、密码不进入输出和重复解锁拒绝。未执行真实业务审批或企业微信发送。

## 给单位电脑上的 Codex

请验证本目录绿色版的本地核心业务命令。先阅读 LOCAL_TOOLS.md 和本文件。
不要修改用户配置、删除 LocalCommands 数据、调用旧审批入口或使用 --test-mode。
第一阶段只做查看和拒绝路径验证。没有用户对具体 task_id 的明确审批授权，禁止运行有效的 approve 命令。
不能为了测试而审批真实事项。任何未知结果或登记失败都不能通过再次审批解决。

## 范围与前提

- 仅支持核心业务系统 `/amcs/index.htm` 内的“待办事宜处理”详情标签。OA、弹出的独立详情窗口不在本轮审批范围内。
- 使用本轮更新的完整 dist_green 目录，不要只复制主程序。需要新的 ReadProjects.ps1、ApprovalRunner.exe 和 _internal。
- 默认连接 `http://localhost:9222`，保留单位已可用的浏览器快捷方式和用户资料目录。不要强制改成 127.0.0.1。
- 程序读取本机 `%LOCALAPPDATA%/com.yourcompany.approvaltool/Settings/config.json` 及同目录 push-settings.json；不存在时沿用随包配置。不要覆盖单位配置。
- 先在前端核对登记开关和目录。审批期间不要操作其他标签页，不要并发运行前端审批或其他浏览器自动化。命令锁只覆盖这些本地命令，不能锁住人工或前端操作。
- 查看凭证15分钟有效，绑定任务编号、系统来源、提取字段和有效配置。配置或字段变化后必须重新查看、重新取得用户确认。

## 第一阶段：不审批

遇到“当前会话已经失效,屏幕已锁定,请激活!”时，可在绿色版目录运行 `./ReadProjects.ps1 -Action unlock`，在本机隐藏输入密码。此命令只处理唯一匹配的核心系统锁屏，不审批、不登记；不要把密码写进命令行或聊天记录。`session_unlocked` 只表示锁屏弹窗已消失，随后仍要用 list 确认待办可读。其他登录页、密码过期弹窗或多个锁屏页面由用户手动处理。

在绿色版目录的 PowerShell 中逐条运行，替换占位符，不要整段批量执行：

```powershell
./ReadProjects.ps1 -Action list
./ReadProjects.ps1 -Action view -TaskId '实际任务编号'
```

检查 `pending_list` 的完整性、分页数、任务编号和标题。`complete=false` 不能当成完整清单。
检查 `project_view` 的 `read_only=true`、records 与页面一致，并保留 `review_token`。
将提取信息汇总给用户，缺少的正文/附件必须明确说明。确认没有审批弹窗、登记文件或企业微信新增记录。

无风险拒绝测试：只运行缺少 ConfirmTaskId 的命令，应在连接浏览器前报错，不点击任何按钮：

```powershell
./ReadProjects.ps1 -Action approve -TaskId '实际任务编号' -ReviewToken '刚才的凭证'
./ReadProjects.ps1 -Action status -TaskId '实际任务编号' -ReviewToken '刚才的凭证'
```

此时 status 应返回 `approval=not_started`。不要通过补齐参数自动继续。

## 第二阶段：用户明确授权一个任务后

先向用户展示任务编号、标题、提取字段、数量、业务类型和启用的登记通道，并取得“同意该任务并登记”的明确授权。
再次确认浏览器为同一账号、同一核心系统。凭证过期或字段改变时重新展示，不得静默重新授权。

```powershell
./ReadProjects.ps1 -Action approve -TaskId '获授权的任务编号' -ReviewToken '对应的有效凭证' -ConfirmTaskId '同一个任务编号' -Quantity 1 -BusinessType '用户确认的业务类型'
```

Quantity 可选1到10，默认1；省略 BusinessType 时保留提取值。
一次命令仅审批一个任务，但合同类可能登记多条记录。程序先检查登记配置，再核验任务与已查看信息，执行现有同意、意见、确认、部门选择和最终确认流程。
随后会刷新核心首页核对完整待办，这会刷新该首页的内部标签。

## 结果解释与人工核对

- `approval_result.approval=confirmed`：最终确认步骤返回且刷新后的完整待办无此任务。这只是前端证据，不是后台审批回执。**首次验证必须打开系统审批历史，核对同一 task_id 的办理结果、人员和意见。** 若系统有筛选、委托账号切换或列表初始化空窗，不应仅凭任务消失认定成功；记录页面结构以补充更强的成功标志。
- `approval=unknown`：可能未提交，也可能已提交但未确认。程序不登记、不自动重试。停止自动化，人工查看流程历史；不要删除防重复记录来绕过保护。
- `registration` 按记录索引分别列出 Obsidian、企业微信的成功/失败。关闭的通道不出现，空通道表示未启用登记，不是新增记录成功。
- 已审批但登记失败：保留成功通道的记录，人工补未完成通道。本轮没有补登记命令，禁止重新执行审批。
- 退出码0表示命令正常完成；approve 的退出码2表示审批待核实或登记未全部完成；退出码1表示前置拒绝/异常。以JSON结果为准，不只看终端最后一行。

网络中断、进程异常或结果丢失时，用只读状态命令查询，不会连接浏览器或重新审批：

```powershell
./ReadProjects.ps1 -Action status -TaskId '任务编号' -ReviewToken '对应凭证'
```

状态记录位于 `%LOCALAPPDATA%/com.yourcompany.approvaltool/LocalCommands/approvals.sqlite3`，包含业务字段，应留在本机，不上传公开仓库。它独立于软件目录，也不按5天日志规则清理，以保留防重复保护。保护仅覆盖同一Windows用户本机，不能阻止其他电脑或前端再次操作。

审批成功后可再次执行同一条 approve 验证拒绝路径：只应报告已有审批尝试记录，不应再次点击，也不应重复登记。若首次结果 unknown，则只查 status，不做真实重试测试。

## 回传验收报告

请提供：版本目录及执行组件SHA256；脱敏后的命令参数（隐藏凭证、Webhook和账号）；list/view/approve/status 的JSON事件；系统审批历史人工核对结果；各登记通道的记录数量；是否出现委托弹窗、异步加载、弹窗在顶层还是详情iframe内。
异常时附准确时间、错误文本及必要的脱敏截图，不发送完整配置或浏览器资料目录。

通过条件：查看零审批/零登记；未确认时拒绝；指定任务正确办理且系统历史吻合；各通道结果真实；相同任务重复调用被拒绝；旧前端审批行为无回归。
本地开发验证均使用隔离模拟页面，不能替代单位真实环境验收。
