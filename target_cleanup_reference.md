# target/ 目录删除参考指南

> 生成时间：2026-05-08
> 适用项目：approval-automation-vue/proto（Tauri + Vue + Python 桌面应用）

---

## 一、直接后果（删完立刻发生什么）

| 方面 | 影响 |
|------|------|
| **Git 状态** | **无影响**。`target/` 在 `.gitignore` 里，Git 本来就不管它 |
| **磁盘空间** | **立刻释放约 5.5 GB**（debug 3.9G + release 1.6G） |
| **现有程序** | 如果正在运行 `target/debug/approval-tool.exe` 或 `target/release/approval-tool.exe`，**已启动的实例不受影响**（Windows 会保持文件句柄），但文件实体已删，重启后无法再从这个路径启动 |
| **安装包** | `target/release/bundle/` 里的 `.msi` 和 `.exe` 安装包会被一并删除，如果还想分发给别人，需要提前备份 |

---

## 二、对开发工作流的影响

### 场景 1：日常开发（`cargo tauri dev`）
**影响：中等，耗时几分钟**

Tauri dev 命令会重新调用 `cargo build`（debug 模式）。删除后首次启动：
1. Cargo 重新解析依赖（`Cargo.lock` 还在，版本不变）
2. 重新下载/解压所有 Rust crate（依赖库）到本地缓存
3. 重新编译 Rust 代码和 Tauri 框架代码
4. **耗时**：取决于机器性能，通常 **3~10 分钟**

之后的启动恢复正常（因为重新生成了 `target/debug/`）。

### 场景 2：打包发布（`cargo tauri build`）
**影响：较大，耗时十几分钟**

Release 编译本身就很慢，删了 `target/release/` 后：
1. 所有 release 模式的依赖要重新编译（release 优化级别高，编译比 debug 慢很多）
2. 重新链接、打包资源
3. **耗时**：通常 **10~30 分钟**
4. 最终还是会生成同样的 `approval-tool.exe` 和安装包

---

## 三、对项目配置/数据的影响

**完全没有影响**。`target/` 里全是"可重新生成的机器文件"，不存任何配置或数据：

- 业务配置在 `src-tauri/python/config.json`（源代码目录，安全）
- Python 源码在 `src-tauri/python/src/`（安全）
- Vue 前端源码在 `src/`（安全）
- 包管理配置 `Cargo.toml`、`package.json`（安全）

---

## 四、部分删除 vs 全部删除

| 操作 | 释放空间 | 后果 |
|------|----------|------|
| **只删 `target/debug/`** | ~3.9 GB | 保留 release 打包能力。下次开发需重编 debug，但 build 不受影响 |
| **只删 `target/release/`** | ~1.6 GB | 保留开发能力。下次 build 需重编 release（最慢的部分） |
| **删整个 `target/`** | ~5.5 GB | 开发和 build 都要重新来过 |
| **只删 `target/release/bundle/` 以外的内容** | ~5.4 GB | **推荐**。保留安装包，释放其余空间 |

---

## 五、恢复方法

```bash
# 重新生成 debug（开发用）
cd src-tauri
cargo build

# 重新生成 release 并打包（发布用）
cargo tauri build
```

不需要任何额外操作，Cargo/Tauri 会自动处理。

---

## 六、内部子目录详解

| 子目录 | 用途 |
|--------|------|
| **`approval-tool.exe`** | 最终的可执行程序（桌面应用本体） |
| **`approval_tool.pdb`** | Windows 调试符号文件，崩溃时用来定位代码位置 |
| **`.fingerprint/`** | Cargo 用来判断"这个依赖是否需要重新编译"的指纹记录 |
| **`build/`** | 编译脚本（build.rs）的输出，比如生成一些自动代码 |
| **`deps/`** | 所有依赖库编译后的 `.rlib` 文件，这是体积最大的部分 |
| **`incremental/`** | 增量编译缓存，只改一行代码时不用全量重编，靠它加速 |
| **`bundle/`** | **最终安装包**（`ApprovalTool_0.0.0_x64_en-US.msi` 和 `ApprovalTool_0.0.0_x64-setup.exe`） |
| **`nsis/`、`wix/`** | 两种打包工具（NSIS / WiX）的临时文件 |
| **`resources/`** | 打包时嵌入的资源文件 |
| **`python/`** | Tauri 打包时把 Python 脚本放进去的目录 |

---

## 七、总结建议

| 你的情况 | 建议 |
|----------|------|
| 磁盘空间紧张 | 把整个 `target/` 删掉，释放 5.5 GB |
| 还想保留安装包 | 先把 `target/release/bundle/` 复制出来，再删 `target/` |
| 正在频繁开发调试 | 不要删，否则每次 `cargo tauri dev` 都要等几分钟 |
| 项目已稳定，暂时不开发 | 大胆删，需要时再编译 |

**一句话：删了不会坏，只是下次编译要等一等。**
