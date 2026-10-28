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
