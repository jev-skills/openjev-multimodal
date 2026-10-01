# openjev-multimodal skill

An agent skill for building with [OpenJev Multimodal](https://github.com/jev-skills/openjev-multimodal),
the local Jev-compatible SystemOne API. It teaches an agent (Claude Code, Codex, or any
tool that reads `AGENTS.md`) how to start and check the service, call it with text and
images, design Noul, Choice and Score questions, size images for the vision encoder,
and read latency and probabilities.

| File | Contents |
| --- | --- |
| `SKILL.md` | When to use it and the working guide |
| `references/api.md` | Request, answers, headers, limits and errors |
| `references/design.md` | Question and image design, with measured lessons from the Tetris example |
| `scripts/openjev.py` | `health`, `ask` and `image` commands; Python standard library only |

## Install

With [OpenSkills](https://github.com/numman-ali/openskills) (Node.js 20.6+):

```bash
# from GitHub: install for every project on this machine
npx openskills install jev-skills/openjev-multimodal/skills/openjev-multimodal -g -y

# from a clone of the repository
npx openskills install ./skills/openjev-multimodal -g -y    # or: npm run skill:install
```

`-g` installs to `~/.claude/skills`; leave it out to install into the current project,
or add `--universal` to use `.agent/skills` for agents that read `AGENTS.md`. Then run
`npx openskills sync` to list the skill in `AGENTS.md`, and
`npx openskills read openjev-multimodal` to print it. Update or remove it later with
`npx openskills update openjev-multimodal` and `npx openskills remove openjev-multimodal`.

Without OpenSkills, copy or link the folder into your agent's skill directory, for
example `~/.claude/skills/openjev-multimodal` or `~/.codex/skills/openjev-multimodal`.

## 安装（中文）

```bash
# 从 GitHub 安装到本机（所有项目可用）
npx openskills install jev-skills/openjev-multimodal/skills/openjev-multimodal -g -y

# 从本地克隆安装
npx openskills install ./skills/openjev-multimodal -g -y    # 或：npm run skill:install
```

`-g` 安装到 `~/.claude/skills`；去掉 `-g` 则安装到当前项目；加 `--universal` 则安装到
`.agent/skills`，供读取 `AGENTS.md` 的智能体使用。之后运行 `npx openskills sync` 把技能写入
`AGENTS.md`。不使用 OpenSkills 时，直接把本目录复制或链接到 `~/.claude/skills/openjev-multimodal`
或 `~/.codex/skills/openjev-multimodal` 即可。

The skill needs a running service for its examples: see the
[quickstart](https://jev-skills.github.io/openjev-multimodal/guide). MIT licensed.
