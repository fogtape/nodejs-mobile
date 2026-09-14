# 来源与差异说明（本副本）

本仓库是 **方案 A（一次性引入配方）** 的产物：把上游的"配方"复制进自己的仓库，
此后构建链路只依赖 `nodejs/node` 官方源码，不再依赖任何第三方 fork 的产物。

## 来源

- 配方来源：`digidem/nodejs-mobile` 的 `recipe` 分支，提交 `de44804`（2026-09-03）。
- 血统：该 fork 派生自官方 `nodejs-mobile/nodejs-mobile`。
- 许可：Node.js 及本配方系列均为 MIT 系许可，完整文本见本仓库 `LICENSE`。

## 构建时实际拉取的内容

`scripts/prepare.sh` 的默认上游是官方仓库，不存在任何第三方中间产物：

```
UPSTREAM_REPO=${UPSTREAM_REPO:-https://github.com/nodejs/node.git}
```

流程为：浅克隆 `nodejs/node` 的指定 tag（见 `upstream-base.txt`，当前 `v24.20.0`）
→ 应用 `patches/` 补丁系列 → 覆盖 `mobile-src/` → 与 `expected-tree.txt` 校验整树哈希。

## 相对上游配方的差异

| 改动 | 原因 |
|---|---|
| 删除 `.github/workflows/browserstack-smoke.yml`，并移除 `build.yml` 中的 `real-device-smoke-android` / `real-device-smoke-ios` 两个 job 及 `publish.needs` 中的对应项 | 本仓库没有 `BROWSERSTACK_USER` / `BROWSERSTACK_PW` 凭据；模拟器/模拟器 smoke、curated 设备测试与 full device suite 仍然作为发布门禁保留 |
| 删除 `.github/workflows/cache-credentials.yml` | 该 workflow 用于探测 Cloudflare R2 的 sccache 凭据，本仓库没有 R2 secrets |
| `upstream-base` 检查降级：仓库内没有该分支时只告警不失败；分支存在但指向错误提交时仍然报错 | 建立该分支需要推送 nodejs/node 的完整历史（约 1.5 GB）。本仓库的发布 tag 直接建立在物化树上，不依赖这条分支的祖先关系；它只作为"基线漂移"的提示保留 |
| 删除 `.github/dependabot.yml` | 本仓库是构建配方镜像，不需要自动依赖升级 PR |
| 发布路径同样允许复用 `actions/cache` 里的 libnode 构建产物（上游只在非发布路径复用） | 上游的目的是保证"发布产物是本次运行编译出来的"。本仓库没有不可信贡献者、也没有跨分支共享缓存，且缓存 key 覆盖全部构建输入（src/deps/lib/tools 目录树 + gyp/configure 文件 + 链接参数与 targetSdk），命中不会改变产物内容，只避免"仅改测试/文档也要重编 1.5–3 小时" |
| 新增 `LICENSE` | `recipe` 分支本身不含许可文件，而它会重建并分发 Node.js 源码树 |

其余文件（补丁系列、`mobile-src/` 覆盖层、`scripts/`、其余 workflow）与来源提交一致。

说明：`docs/BUILDING.md` 仍会提到"CI 编译器缓存"与 `cache-credentials.yml`，
那是上游仓库的凭据体系；在本副本中 sccache 后端为空，构建回退为本机磁盘缓存。
