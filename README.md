# 每日新闻自动爬取与总结系统

一个用 Python 编写的“小而美”工具：自动爬取新闻站点、调用 AI（DeepSeek / OpenRouter / ModelScope 三选一）生成每条“摘要”与“今日热点总结”，输出为 Markdown 文件；同时内置可视化前端与后端 API，支持本地浏览与一键生成。

## 你将获得

- 自动化：一键获取当日新闻 + AI 摘要 + 热点总结
- 可定制：自定义新闻源、数量、模型与参数
- 可追踪：生成日志、调试文件，排障简单清晰
- 可靠性：API 出错时自动降级“本地应急摘要”，不破坏报告结构

---

## 环境与目录结构

- Python 3.8+（建议）
- 依赖安装：见下文“快速开始”

项目结构（关键文件）：

```
news_crawler/
├─ main.py                  # 命令行入口：爬取 + 调用AI + 生成Markdown
├─ app.py                   # 后端服务（FastAPI）：提供API并挂载前端
├─ requirements.txt         # 依赖清单
├─ README.md                # 说明文档（本文件）
├─ .env.example             # 环境变量示例（请复制为 .env 并填写）
├─ .env                     # 你的私密配置（需自行创建，已被忽略）
├─ HTML/                    # 前端页面（静态资源）
│  ├─ index.html
│  ├─ script.js
│  └─ style.css（可选）
├─ news_output/             # 输出目录
│  └─ 2025年10月19日每日新闻.md
├─ news.log                 # 运行日志
└─ debug_api_response.json  # 最近一次 API 原始返回（调试用）
```

---

## 快速开始（Windows PowerShell）

1) 创建并激活虚拟环境（可选但推荐）

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
```

2) 安装依赖

```powershell
python -m pip install -U pip ; pip install -r requirements.txt
```

3) 准备配置文件

- 复制 `.env.example` 为 `.env`，并按注释填写你的密钥与端点

4A) 命令行运行（生成当日 Markdown）

```powershell
python .\main.py
```

4B) 启动可视化 Web 界面（推荐用于查看历史与一键生成）

```powershell
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

打开浏览器访问：http://127.0.0.1:8000/

生成成功后，你会在 `news_output/` 看到“YYYY年MM月DD日每日新闻.md”，包含：
- 每条新闻的【标题】【摘要】【原文链接】
- 文末的“今日热点总结”

若外部 API 临时不可用（配额/网络/配置问题），程序会自动生成“本地应急摘要”，保证报告结构完整可读。

---

## 配置说明（.env）

三种服务任选其一，变量名保持一致（推荐 DeepSeek 官方或 OpenRouter）：

```
# DeepSeek 官方（推荐）
API_KEY=your_deepseek_api_key
API_URL=https://api.deepseek.com/v1/chat/completions
API_MODEL=deepseek-chat

# OpenRouter（可选）
# API_KEY=sk-or-xxxx
# API_URL=https://openrouter.ai/api/v1/chat/completions
# API_MODEL=deepseek/deepseek-chat-v3.1:free

# ModelScope（可选，OpenAI 兼容接口）
# API_KEY=ms-xxxx
# API_URL=https://api-inference.modelscope.cn/v1/chat/completions
# API_MODEL=deepseek-ai/DeepSeek-V3.1
# 注：若只填 https://api-inference.modelscope.cn/v1，程序会自动补 /chat/completions

# 可选参数（不填则使用默认值）
# API_TEMPERATURE=0.7
# API_MAX_TOKENS=2000
# API_MAX_RETRIES=2

# 若需代理（公司/校园/本地代理）
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890

# 新闻获取配置
MAX_ARTICLES=10  # 最大获取新闻数量
```

提示：程序会根据 `API_URL` 自动推断提供商并给出合理的默认模型名，降低配置出错概率。

提供商与模型名参考：
- DeepSeek 官方：API=https://api.deepseek.com/v1/chat/completions，模型=deepseek-chat
- OpenRouter：API=https://openrouter.ai/api/v1/chat/completions，模型=deepseek/deepseek-chat-v3.1:free
- ModelScope：API=https://api-inference.modelscope.cn/v1/chat/completions，模型=deepseek-ai/DeepSeek-V3.1

---

## Web 界面与 API（已与前端对接）

前端位于 `HTML/`，后端为 `app.py`（FastAPI）。默认启用 CORS 以方便本地开发（生产环境请按需收紧）。

- GET /api/health               健康检查
- GET /api/news-list            列出历史日期（从 news_output 扫描）
- GET /api/news-detail?date=YYYY-MM-DD  获取某日 Markdown 与摘要
- POST /api/generate-news       触发抓取+AI摘要生成（后台异步线程）
- GET /api/generate-status      轮询生成进度（idle/crawling/processing/completed/failed）

常见问题：
- 首次无数据：先点“生成今日新闻”，完成后左侧会出现当天日期；
- 端口冲突：修改 `--port`，前端走相对路径无需改动；
- CORS：开发期允许所有来源，生产建议白名单；
- 代理：如需外网代理，在 `.env` 配置 HTTP_PROXY/HTTPS_PROXY。

---

## 工作原理（通俗版）

1) NewsGetter：抓取新闻列表页 HTML，用 CSS 选择器提取 标题/链接/时间/来源
2) NewsProcessor：把新闻转成 Prompt，调用 AI 接口（OpenAI 兼容），并解析响应
3) ReportGenerator：渲染为 Markdown 并按日期保存到 `news_output/`

关键日志与调试：
- `news.log`：全流程日志（抓取数量、API 错误等）
- `debug_api_response.json`：最近一次 API 的原始返回（定位解析失败原因）

---

## 自定义新闻源（CSS 选择器）

在 `main.py` 顶部的 `news_sources` 列表中添加/修改配置：

```python
news_sources = [
    {
        'name': '凤凰新闻',
        'url': 'https://news.ifeng.com/',
        'base_url': 'https://news.ifeng.com',
        'item_selector': '.news-stream-newsStream-news-item-infor',
        'title_selector': 'h2',
        'link_selector': 'a',
        'time_selector': '.time',
        'source_selector': '.source'
    }
]
```

选取选择器的方法：打开网页 → F12 开发者工具 → 选中元素 → 右键复制 CSS Selector。

---

## 常见问题与排障（FAQ）

1) 报告里没有“摘要/热点总结”？
- 查看 `news.log` 是否有 401/402/404/429/连接错误；
- 打开 `debug_api_response.json` 看真实返回；
- 检查 `.env`：
  - `API_URL` 是否包含 `/v1/chat/completions`；
  - 模型名是否与提供商匹配（见前文“提供商与模型名参考”）；
  - 网络受限时设置 HTTP_PROXY/HTTPS_PROXY。

2) 看到“欢迎消息”（尤其是 ModelScope）或奇怪 JSON？
- 多为端点或模型名不匹配；请按如下设置：
  - API_URL=https://api-inference.modelscope.cn/v1/chat/completions
  - API_MODEL=deepseek-ai/DeepSeek-V3.1（ModelScope 的 Model-Id）

3) 抓不到新闻或数量很少？
- 站点结构可能变了，更新 CSS 选择器；
- 调整 `MAX_ARTICLES`；
- 查看 `debug_*.html` 排查选择器是否匹配。

4) Windows 字符显示异常？
- 使用 UTF-8 打开文件；
- 终端建议使用 Windows Terminal + UTF-8 编码。

---

## 进阶自定义

- 修改摘要风格：编辑 `NewsProcessor.create_prompt` 的提示词；
- 控制篇幅：调整 `.env` 的 `API_TEMPERATURE`、`API_MAX_TOKENS`；
- 更换提供商：替换 `API_URL`、`API_KEY`、`API_MODEL` 即可。

---

## 安全与合规

- 切勿把 `.env`（含密钥）提交到仓库；
- 遵守目标网站 robots 与访问频率要求；
- 内容仅供学习研究，转载需遵守版权与平台规则。

---

## 许可

本项目用于学习交流，可自由使用与改造。如用于生产，建议完善缓存、并发、重试、鉴权与异常告警，并收紧 CORS 与密钥管理。
