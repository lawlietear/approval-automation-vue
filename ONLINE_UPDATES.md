# 绿色版联网更新发布指南

## 当前状态

最新验证：开发机已通过固定Gitee raw入口匿名取得有效2.3.1清单，下载地址与签名均正确。单位电脑应点击“检查更新”验证当前版本无可用更新；无需重新打包或替换EXE。尚未进行真实跨版本升级验证。

2026-09-28发布进展：2.3.1发行版已创建，正式latest.json已推送Gitee main（2ffbb7a）。更新ZIP经匿名下载，与本地签名包SHA256一致，签名复验通过；用户确认单位电脑可匿名下载附件。公开清单读取及单位客户端检查更新尚待确认，真实跨版本升级未验证。以下较早状态记录中的“尚未发布”已由本段取代。

2.1.0 已接入绿色版联网更新框架，不使用安装器。工作台的“设置 / 软件更新”支持检查、查看说明、确认下载和退出后替换程序。

2026-09-28已将版本升至2.3.1，重新构建dist_green/dist_share并内置Gitee入口及更新签名公钥。签名更新ZIP和完整分享ZIP已生成，签名及篡改拒绝验证通过。发行版上传与匿名下载验证仍在进行；latest.draft.json只是本地草稿，不能发布。旧版本首次启用需手动更新，不能把构建完成视为线上发布完成。

开发电脑私钥位于`%USERPROFILE%/.tauri/approvaltool/approval-update.key`，对应公钥为同名`.pub`文件。私钥未设额外口令，目录已限制为当前Windows用户和SYSTEM访问；不要上传私钥，妥善保管，后续发版复用而非重新生成。签名时使用此文件路径及空密码。已用Tauri CLI签名临时文件，并用配置公钥验证文件签名和受信注释，篡改内容验证失败。该测试不是单位网络上的端到端在线升级验证。

## 存放在哪里

### Gitee 发布前检查

目标仓库：https://gitee.com/nate901/approvaltool 。源码推送、发行版附件上传、客户端在线更新是三个独立步骤；推送源码不会自动生成发行版或启用更新。SSH公钥用于发布者推送源码，Tauri签名公钥用于客户端验证更新包，不能混用。

2026-09-28已上传独立脱敏源码快照，并在开发电脑匿名验证原始文件地址返回200及有效JSON。计划清单地址为`https://gitee.com/nate901/approvaltool/raw/main/latest.json`，但latest.json和发行版更新包尚未发布，单位网络也尚未验证。客户端应保存这个稳定Gitee入口，而不是跳转后带过期参数和签名的raw.giteeusercontent.com临时地址。

1. 在仓库发行版上传一个不含配置的测试ZIP，取得真实附件下载地址；不要填写浏览器分享页或自行猜测附件路径。
2. 给`latest.json`安排一个固定HTTPS地址。可以先测试公开仓库的原始文件地址，但必须从未登录浏览器及单位电脑实际验证：返回JSON而非登录页/验证码，ZIP也能匿名直接下载。当前客户端没有Gitee登录流程，不能把发布者Token嵌入客户端绕过登录。
3. 仅在两种下载均验证成功后，将固定JSON地址和独立生成的Tauri签名公钥写入update-source.json，提升版本并重新构建。不满足条件时，Gitee只用于手动发行版下载，在线源另选稳定HTTPS存储。
4. 现有客户端更新源为空，首次启用必须手动替换启用版。后续发布使用下文package-update.py生成签名ZIP及latest.json；先上传ZIP，再更新清单，每次递增版本号。验证一次真实跨版本升级和本机配置保留后，才提供给同事使用。

向新代码托管站推送前，应扫描当前文件及整个Git历史。仅排除未提交的个人配置不足以避免传播旧提交里的Webhook。2026-09-28检查发现原GitHub历史含Webhook链接，Gitee已采用用户确认的独立脱敏快照，不改写GitHub。后续同步不得直接推送原仓库历史到Gitee；只同步检查后的源码变更。建议更换旧Webhook。

推荐使用单位允许访问的腾讯云 COS 或阿里云 OSS，以 HTTPS 提供两个文件：

- `latest.json`：固定地址，告诉程序最新版本、更新说明、ZIP 地址和签名。
- `ApprovalTool-版本号-windows-x86_64.zip`：完整绿色版程序更新包，版本号变化时使用新文件名。

不需要购买云服务器或开发网站后台。最初可使用对象存储提供的 HTTPS 访问域名；有自己的域名时再按云厂商要求绑定。不要购买服务前就假定单位能访问：先上传一个测试文件，让同事在单位网络打开验证。

GitHub 可以保留源码和附加发布包，但如果单位访问受限，不要把它作为客户端唯一下载源。单位已有 HTTPS 文件服务器也能用。普通网盘分享页、要求登录的网页、短期过期的下载链接不能直接用作更新地址。

下载文件可以公开读取，但上传权限只给发布者。更新存储里绝不放 Webhook、API key、个人 config.json、push-settings.json 或 Chrome 资料。不要将云存储管理密钥嵌入客户端。

## 首次启用（只做一次）

1. 创建用于软件发布的存储空间，上传测试文件，确认单位网络可下载。
2. 确定固定地址，例如 `https://你的存储域名/approval/latest.json`。
3. 在开发电脑生成签名密钥。公钥写入程序，私钥只留在发布者安全位置，不进 Git、不发给同事。私钥丢失会导致原用户无法验证后续版本。

在 `proto` 目录执行（路径请换成你自己的安全位置，目录需先创建）：

```powershell
npm.cmd run tauri -- signer generate -w "C:/Users/你的用户名/.tauri/approval-update.key"
```

按提示设置私钥密码。将生成的 `.pub` 文件内容和更新地址填写到 `src-tauri/update-source.json`：

```json
{
  "endpoint": "https://你的存储域名/approval/latest.json",
  "pubkey": "生成的公钥文件内容"
}
```

4. 重新构建绿色版。更新源和公钥编译进程序，普通使用者不需要填写，也不能在设置页替换信任公钥。
5. 先让现有用户退出旧工具，将启用版的 `ApprovalTool.exe` 放到原绿色版目录替换同名文件，再启动一次。它会读取原目录的登记配置，迁移到本机独立配置目录。旧配置文件不会被删除；不要先拿空白分享包覆盖旧配置。
6. 新用户可以直接使用完整的干净分享版。首次配置后，以后更新不需重新设置。

从当前“尚未配置更新源”的 2.1.0 进入启用版，需要这一次手动更新；未提供地址的客户端不可能自行知道未来要去哪里下载。

## 每次发布新版

1. 修改版本号，四处保持一致：`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`、`package.json`、`package-lock.json`。必须高于已发布版本，例如 `2.1.1`。
2. 在项目根目录按现有构建流程生成完整绿色版，并生成干净分享版。确认主程序和 Python 运行组件均为这一版，先运行测试。
3. 在开发机设置签名环境变量，然后生成更新 ZIP 和 `latest.json`。

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY_PATH = "C:/Users/你的用户名/.tauri/approval-update.key"
# 私钥密码通过当前终端环境提供，不写入仓库或脚本，不发送给使用者。
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = "你的私钥密码"

# 在项目根目录运行；调整 source 为已完成且测试过的版本目录。
./.venv/Scripts/python.exe proto/scripts/package-update.py `
  --source dist_share `
  --output proto/release-output/2.1.1 `
  --base-url "https://你的存储域名/approval" `
  --notes "本次更新内容"
```

4. **先上传 ZIP，确认下载正常，再覆盖 latest.json。** 不要反过来，否则同事会看到新版本却下载不到。
5. `latest.json` 设置为不缓存或短缓存；带版本号的 ZIP 可以长期缓存。不要覆盖已经发布的版本 ZIP，也不要使用会自动过期的临时 URL。
6. 同事在“设置 / 软件更新”点击检查，核对说明，勾选确认，再点击“下载并更新”。工具下载后验证签名，退出、替换程序并重新启动；不会关闭 Chrome。

脚本打包主 EXE、Python runner EXE 与 `_internal`，并放入只用于验证的 release.json 版本信息，不打包配置文件。ZIP 内版本也受签名保护，必须与服务器声明相同，防止旧包被冒充新版。外部版本说明沿用 Tauri 的静态更新协议，下载及签名验证使用官方 updater；本程序仅自定义绿色版的文件替换，不调用 MSI/NSIS 安装。

## 用户配置在哪里

正式版：`%LOCALAPPDATA%/com.yourcompany.approvaltool/Settings/`。

- `config.json`：首次迁移的基础业务配置。
- `push-settings.json`：企业微信链接、字段、开关、Obsidian 路径。
- `browser.json`：连接方式、端口和路径。首次也兼容读取旧版 WebView 保存的连接偏好。

后续版本只更新程序，不覆写这些文件。当前版本保留用户完整基础配置，不擅自用新版默认值重置旧字段；将来若需改变配置结构，需要另写有版本意识的迁移，不能粗暴覆盖。

同一 Windows 用户下，不同绿色版目录共享这份配置；不同电脑、不同 Windows 用户不共享。ChromeProfile 保持原有独立目录不变。开发模式使用 Settings-dev，避免修改正式配置。

此版本不提供配置备份、导入或导出功能。旧配置损坏时明确报错，不自动重置。迁移会保留原文件，不是每次生成备份。

## 失败与限制

- 无网络、服务未配置、服务器报错分别显示原因，不冒充“已是最新版”。
- 下载或签名校验失败时不改现有程序；只接受 HTTPS 更新地址。
- ZIP 拒绝路径越界、链接和非程序目录文件，禁止覆盖本机配置。
- 审批运行期间不可更新。用户必须确认退出重启，不静默强制更新。
- 替换时暂存旧程序文件，遇到文件占用等错误尝试恢复；成功后自动清理临时程序文件。这不是配置备份功能。
- 程序目录必须可写。请关闭同目录的其他工具实例；杀毒软件或单位策略阻止更新助手时，不能绕过组织策略，应联系管理员。
- 替换过程中不要强制关机。断电、强制终止更新助手导致的恢复不能等同于普通失败自动恢复；遇到此情况可重新放置完整程序文件，本机 Settings 不受更新包覆盖。
- 尚未在真实外网下载源或单位电脑验证更新闭环。发布前必须先用试用用户完成一次 2.x 到较新版本的在线升级，核对配置、登录资料和审批功能。

## 参考

- Tauri 更新协议和签名：https://v2.tauri.app/plugin/updater/
- 官方下载验证接口：https://docs.rs/tauri-plugin-updater/latest/tauri_plugin_updater/struct.Update.html#method.download
- 腾讯云 COS 域名：https://cloud.tencent.com.cn/document/product/436/6224
- 阿里云 OSS 域名：https://help.aliyun.com/zh/oss/user-guide/access-buckets-via-custom-domain-names
