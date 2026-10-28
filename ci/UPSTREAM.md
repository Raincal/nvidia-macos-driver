# 跟着上游升级（单分支方案）

本分支 `bar-preflight` 长期存在，永远 = «当前上游 tag» + 两个提交：

1. `ci: port the community Intel build chain` —— 构建链（来自 yuanjing-hash 的 fork）
2. `NVRM: port the community BAR preflight` —— 移植（NVRM.cpp 的 7 处 + nvrm_bar_limits.h）

## 升级到新 tag

```bash
git fetch upstream --tags
git rebase v2.7.0          # 冲突基本只在 NVRM.cpp 的那几处
echo v2.7.0 > ci/upstream-tag
git add ci/upstream-tag && git commit --amend --no-edit
git push --force-with-lease
```

`ci/upstream-tag` 只影响 build-proof.json 和 kext 里的版本串，方便回查产物对应哪个上游版本。

## 如果 rebase 太麻烦

`ci/patches/community-bar-preflight.patch` 是移植结果的完整存档，可以直接 `git apply` 到干净的上游 tag 上：

```bash
git checkout -B bar-preflight v2.7.0
git apply ci/patches/community-bar-preflight.patch   # 不行就 3-way：git apply -3
```

## 什么时候彻底不用维护

把移植提交 PR 给 nullmoth 并被合并之后。上游 #185 里第三方已经指出正确修法是
「把 BAR1 放到 (UINT_MAX + 1) * PAGE_SIZE 以下」，社区这套就是这个思路的实现。

---

## 自动构建（定时盯上游）

`.github/workflows/build-barpreflight.yml` 现在按 **tag** 构建，不再按分支构建：

- **定时**：每天 04:00 (CST) 调 upstream 的 `releases/latest`；如果 tag ≠ `ci/upstream-tag`，自动克隆那个 tag、套 `ci/patches/community-bar-preflight.patch`、编译、打包、上传 artifact，成功后把新 tag 提交回本分支。
- **手动**：Actions → *Build NVRM (bar-preflight port)* → Run workflow。可指定 tag（留空=最新）、可关掉打包只出 kext，用来快速验证小改动。

补丁套不上新 tag 时 workflow 会**直接失败**并打印 `STOP: 移植补丁套不上 …`，此时：

```bash
git fetch upstream --tags
git checkout -B tmp v2.7.0
git apply -3 ci/patches/community-bar-preflight.patch   # 手工对齐冲突
git diff > ci/patches/community-bar-preflight.patch     # 回写补丁
```

分支里那份改好的 `NVRM.cpp` 仍然保留，作用是给补丁提供参照和方便 diff，构建本身用补丁而不是用分支里的树。
