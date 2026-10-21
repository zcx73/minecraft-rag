# 项目说明：Minecraft 新手 RAG（本地 Ollama + Qwen3-8B）

一个**不用联网、不用显卡云服务**的 RAG 小项目：把 Minecraft 新手知识切成小块，用 BM25 检索出最相关的几段，再交给本地 Ollama 里的 `qwen3-8b-heretic-Q4_K_M` 生成带出处的回答。

- 模型：`qwen3-heretic:latest`（GGUF Q4_K_M，4.68 GB，本机 Ollama 已加载）
- 语言：Python 3.12
- 检索：jieba 分词 + BM25（零向量模型依赖），可选语义重排
- 知识库：11 篇中文文档 / 96 个检索块，覆盖从第一天到打末影龙的新手主线

---

## 1. 目录结构

```
minecraft-rag/
├─ data/docs/            # 知识库原文（Markdown，改这里就能换领域）
├─ src/
│  ├─ config.py          # 所有路径与模型参数
│  ├─ ingest.py          # 按标题切块
│  ├─ tokenizer.py       # 中文分词 + 同义词扩展（jieba 可选）
│  ├─ retrieve.py        # BM25 索引 + 检索 + 可选语义重排
│  ├─ prompt.py          # 系统提示词与上下文拼装
│  ├─ llm.py             # 调用 Ollama /api/chat（流式）
│  ├─ rag.py             # 检索→生成 的完整流程
│  └─ cli.py             # 命令行入口
├─ tests/test_rag.py     # 5 个离线测试（不依赖模型）
├─ scripts/
│  ├─ setup.bat          # 一键建环境 + 装依赖 + 建索引
│  ├─ run.bat            # 启动问答
│  ├─ fetch_wheels.py    # 把依赖包下载到 wheels/ 供离线安装
│  └─ install_jieba.py   # jieba 安装失败时的手动兜底（见第 5 节）
├─ storage/              # 切块与索引（自动生成）
├─ wheels/               # 依赖轮子缓存（可删）
└─ requirements.txt
```

## 2. 三步跑起来

```bat
:: 1) 启动 Ollama（如果还没开）
ollama serve

:: 2) 准备环境（建 venv、装依赖、建索引）
scripts\setup.bat

:: 3) 提问
scripts\run.bat "第一天晚上怎么活下来"
scripts\run.bat            :: 进入连续对话
```

输出长这样：

```
🔍 检索到的资料：
   [1] 04-挖矿与矿物.md · 各矿物的最佳高度（1.00）
   [2] 03-合成与工具.md · 木→石→铁→钻石：工具升级路线（0.79）

💬 回答：
钻石在 Y=-58 附近最密集 [1]，需要铁镐才能挖出 [1]。

📚 来源：
   [1] 04-挖矿与矿物.md · 各矿物的最佳高度
⏱  首字 7.3s，总耗时 7.8s
```

## 3. RAG 流程（这个项目到底做了什么）

```
问题
 └─> jieba 分词 + 同义词扩展          tokenizer.py
      └─> BM25 打分，取前 12 条候选     retrieve.py
           └─> 标题命中加权、同小节去重
                └─> 取前 4 条拼成 [1][2] 编号的上下文   prompt.py
                     └─> Ollama /api/chat 流式生成       llm.py
                          └─> 带 [编号] 的回答 + 来源清单  rag.py
```

三个关键设计：

1. **只喂相关片段**。模型上下文只有 8k，整篇文档塞进去既慢又容易"看丢"；500 字一块最合适。
2. **强制引用**。提示词要求每条结论标 `[编号]`，你能立刻回溯到是哪篇文档说的，不容易被编。
3. **资料里没有就说没有**。系统提示词明确禁止编造数值和版本特性，越界问题直接拒答。

## 4. 常用命令

```bat
:: 改完 data/docs 里的文档后，必须重建索引
.venv\Scripts\python -m src.cli build

:: 问一句
.venv\Scripts\python -m src.cli ask "红石中继器有什么用"

:: 看检索细节 / 显示思考过程 / 语义重排
.venv\Scripts\python -m src.cli ask "怎么刷附魔书" --top-k 6 --think --hybrid

:: 环境自检（依赖、索引、模型）
.venv\Scripts\python -m src.cli doctor

:: 跑测试
.venv\Scripts\python -m pytest
```

## 5. 常见问题

**Q：Ollama 报 `model not found` / 连接失败？**
先确认服务在跑：`ollama list` 能看到 `qwen3-heretic:latest`。本项目默认连 `http://127.0.0.1:11434`，改端口就设环境变量 `OLLAMA_HOST`。

**Q：8G 显存能跑 8B 吗？**
能。Q4_K_M 权重 4.68 GB，加上 8k 上下文和 KV 缓存大约 6~7 GB，你的 RTX 4060 Laptop（8 GB）实测 46 tok/s。显存不够时 Ollama 会自动把部分层放到 CPU，速度会掉到 5~10 tok/s。

**Q：回答很慢 / 首字很慢？**
- 第一次请求要加载模型（10~20 秒），之后常驻。
- `config.py` 里 `num_ctx=8192` 可以降到 4096 换速度。
- 加 `--think` 会让模型先"思考"再回答，更慢但更准。

**Q：pip 装 `jieba` 失败？**
`jieba` 只有源码包（没有 wheel），个别环境编译会失败。用兜底脚本：

```bat
.venv\Scripts\python scripts\install_jieba.py
```

它会把 `jieba` 直接解压进虚拟环境的 `site-packages`。装不上也不影响运行——`tokenizer.py` 会自动退化成"单字+二元组"分词，BM25 照样能用。

**Q：完全离线怎么装依赖？**
在一台能上网的机器上：`python scripts/fetch_wheels.py`，把 `wheels/` 整个拷过来，然后：
```bat
.venv\Scripts\python -m pip install --no-index --find-links wheels -r requirements.txt
```

**Q：中文终端乱码？**
CLI 已经强制 UTF-8 输出。如果还乱码，先执行 `chcp 65001`。

## 6. 怎么换成别的领域

1. 删掉 `data/docs/*.md`，放入你自己的 Markdown（一级标题当文档名，二级标题当小节）。
2. 改 `src/prompt.py` 里的 `SYSTEM_PROMPT`（角色、语气、拒答规则）。
3. 改 `src/tokenizer.py` 里的 `SYNONYMS` 和 `GAME_TERMS`（你的领域专有名词）。
4. `python -m src.cli build` 重建索引。

不用改一行检索代码。

## 7. 已知取舍

- **用 BM25 而不是向量库**：省掉 embedding 模型（几百 MB）和向量数据库，启动快、可解释（能看到每条命中多少分）。缺点是"同义不同词"要靠 `SYNONYMS` 手工补。
- **`--hybrid` 用聊天模型算向量**：能跑，但质量不如专门的 embedding 模型（如 `bge-m3`、`nomic-embed-text`）。想要更好的语义检索，拉一个 embedding 模型再替换 `retrieve.py` 里的 `ollama_embed` 即可。
- **模型是 heretic 微调版**：无审查、说话直接，偶尔会加戏。提示词里已经收紧了"只依据资料"，但不能 100% 避免。

## 8. 知识库覆盖范围

| 文档 | 内容 |
|---|---|
| 01-开局与第一天 | 模式选择、出生点、第一天步骤、床与死亡 |
| 02-操作与界面 | 键位、HUD、坐标、难度、基岩版差异 |
| 03-合成与工具 | 2×2/3×3、工具等级、熔炉、存储 |
| 04-挖矿与矿物 | 1.18+ 矿物高度表、三种挖矿法、安全守则 |
| 05-食物与饥饿 | 饥饿/饱和度机制、食物表、农业 |
| 06-怪物与夜晚安全 | 刷怪规则、常见怪对策、保命四件套 |
| 07-村庄与村民交易 | 职业表、绿宝石经济、袭击 |
| 08-附魔与装备 | 附魔台/书架、常用附魔、铁砧 |
| 09-下界与末地 | 传送门、远古残骸、打龙、鞘翅 |
| 10-红石入门 | 五个基础元件、三个小项目 |
| 11-联机与常见问题 | 联机、指令、种子、FAQ |
