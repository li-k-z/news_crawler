# 每日新闻自动爬取与总结系统（新手友好版）

一个用 Python 写的“小而美”工具：自动爬取新闻站点、调用 AI（DeepSeek / OpenRouter / ModelScope 三选一）生成摘要与“今日热点总结”，最后输出为 Markdown 文件。

## 你将获得

- 自动化：一键获取当日新闻 + AI 摘要 + 热点总结
- 可定制：自定义新闻源、数量、模型与参数
- 可追踪：生成日志、调试文件，便于排障
- 可靠性：API 出错时自动降级到“本地应急摘要”，报告结构不破坏

---

## 运行前提

- Python 3.8+（建议）
- 安装依赖：
   ```
   pip install -r requirements.txt
   ```
- 准备 `.env` 配置文件（见下文）

目录结构示例：

```
news_crawler/
├─ main.py                 # 主程序
├─ requirements.txt        # 依赖
├─ README.md               # 说明文档（本文件）
├─ .env.example            # 环境变量示例
├─ .env                    # 你的私密配置（需自行创建）
├─ news_output/            # 输出目录
│  └─ 2025年10月19日每日新闻.md
├─ news.log                # 运行日志
└─ debug_api_response.json # 最近一次 API 返回（调试用）
```

---

## 配置说明（.env）

三种服务任选其一，变量名保持一致：

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

提示：程序会自动根据 `API_URL` 推断提供商，设置合理默认模型，减少配置出错概率。

---

## 一键运行

```bash
python main.py
```

运行成功后，你会在 `news_output/` 看到一个以当天日期命名的 Markdown 文件，内容包含：
- 每条新闻的【标题】【摘要】【原文链接】
- 文末的“今日热点总结”

若外部 API 临时不可用（配额/网络/配置问题），程序会自动生成“本地应急摘要”，确保报告结构完整。

---

## 前后端联动（可视化界面）

本项目内置了一个简洁的前端（HTML/index.html + script.js + style.css），并通过 FastAPI 提供后端接口，可本地直接预览：

1) 安装依赖并启动后端服务

```powershell
python -m pip install -r requirements.txt ; uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

2) 打开浏览器访问

- http://127.0.0.1:8000/

3) 接口说明（前端已对接）

- GET /api/health            健康检查
- GET /api/news-list         列出已生成的日期（从 news_output 扫描）
- GET /api/news-detail?date=YYYY-MM-DD  获取某日 Markdown 与摘要
- POST /api/generate-news    触发抓取+摘要生成流水线（后台线程）
- GET /api/generate-status   轮询生成进度（idle/crawling/processing/completed/failed）

4) 常见问题

- 首次运行无数据：先点击“生成今日新闻”，等待完成后侧边栏会出现当天日期；
- API 失败：查看 `news.log` 与 `debug_api_response.json`，多半是 API_URL/模型名/密钥/代理配置问题；
- 端口被占用：修改启动命令的 `--port`，前端走相对路径无需改动；
- CORS：后端已开启允许所有来源（方便本地开发）。生产可按需收紧白名单；
- 代理网络：如需外网代理，请在 `.env` 配置 HTTP_PROXY/HTTPS_PROXY。

---

## 工作原理（通俗版）

1. NewsGetter：抓取新闻列表页 HTML，用 CSS 选择器提取标题/链接/时间/来源
2. NewsProcessor：把新闻变成一个对话提示词（prompt），调用你配置的 AI 接口
3. ReportGenerator：把 AI 的输出（或本地应急摘要）渲染为 Markdown，并按日期保存

关键日志与调试：
- `news.log`：全流程日志（抓取数量、API 调用错误等）
- `debug_api_response.json`：最近一次 API 的原始返回（用于分析解析失败原因）

---

## 自定义新闻源（CSS 选择器）

在 `main.py` 顶部的 `news_sources` 列表中添加或修改配置：

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

找选择器方法：打开网页 → F12 开发者工具 → 选中元素 → 复制 CSS Selector。

---

## 常见问题与排障

1) 报告里没有“摘要/热点总结”怎么办？
- 看 `news.log` 是否有 401/402/404/429/连接错误
- 打开 `debug_api_response.json` 看实际返回
- 检查 `.env`：
   - `API_URL` 是否包含 `/v1/chat/completions`
   - 模型名是否与提供商匹配（见上方配置）
   - 如网络受限，请设置 HTTP_PROXY/HTTPS_PROXY

2) 看到“欢迎消息”或奇怪 JSON（特别是 ModelScope）怎么办？
- 说明端点或模型名没对上。
- 按 README 的 ModelScope 配置使用：
   - API_URL=https://api-inference.modelscope.cn/v1/chat/completions
   - API_MODEL=deepseek-ai/DeepSeek-V3.1（ModelScope 的 Model-Id）

3) 抓不到新闻或数量很少？
- 网站结构可能变了，更新 CSS 选择器
- 适当调整 `MAX_ARTICLES`

4) 字符乱码或输出为问号？
- 确保系统与编辑器使用 UTF-8 打开文件

---

## 进阶自定义

- 修改摘要风格：编辑 `NewsProcessor.create_prompt` 中的提示词
- 控制输出篇幅：调整 `.env` 的 `API_TEMPERATURE`、`API_MAX_TOKENS`
- 换别的 AI 服务商：只需换 `API_URL`、`API_KEY`、`API_MODEL`

---

## 安全与合规

- 勿把 `.env`（含密钥）提交到仓库
- 遵守目标新闻网站的 robots 与访问频率要求
- 摘要仅供学习与研究，转载请遵守版权与平台规则

---

## 许可

本项目用于学习交流，可自由使用与改造。若用于生产，请自行完善缓存、并发、重试策略与异常告警。
