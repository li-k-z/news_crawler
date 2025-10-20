import os
import re
import threading
from datetime import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 复用现有业务逻辑类
from main import NewsGetter, NewsProcessor, ReportGenerator


app = FastAPI(title="News Crawler API", version="1.0.0")

# CORS：便于本地/跨源调试；生产可改为白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 生成状态（简单内存状态机）
gen_status_lock = threading.Lock()
gen_status: Dict[str, Optional[str] | int] = {
    "status": "idle",      # idle|crawling|processing|completed|failed
    "progress": 0,          # 0~100
    "message": "",         # 可读状态
    "error": "",           # 失败信息
}


def set_status(status: str, progress: int, message: str = "", error: str = ""):
    with gen_status_lock:
        gen_status["status"] = status
        gen_status["progress"] = progress
        gen_status["message"] = message
        gen_status["error"] = error


def parse_date_from_filename(filename: str) -> Optional[str]:
    """从 'YYYY年MM月DD日每日新闻.md' 提取 ISO 日期（YYYY-MM-DD）。"""
    m = re.match(r"^(\d{4})年(\d{2})月(\d{2})日每日新闻\.md$", filename)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{y}-{mo}-{d}"


def find_news_file_by_date(date_str: str, output_dir: str = "news_output") -> Optional[str]:
    """根据 ISO 日期找到对应 Markdown 文件路径。"""
    try:
        for name in os.listdir(output_dir):
            iso = parse_date_from_filename(name)
            if iso == date_str:
                return os.path.join(output_dir, name)
    except FileNotFoundError:
        return None
    return None


def extract_summary_from_markdown(md_text: str) -> Optional[str]:
    """从 Markdown 中提取“今日热点总结”作为 summary；若无则取首段。"""
    # 优先找“## 今日热点总结”标题
    parts = re.split(r"\n(?=## )", md_text)
    for part in parts:
        if part.startswith("## 今日热点总结"):
            # 取该段落去掉标题首行
            lines = part.splitlines()
            body = "\n".join(lines[1:]).strip()
            if body:
                return body[:600]
    # 兜底：取第一个正文段落（略过标题行）
    lines = [ln.strip() for ln in md_text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("# ")]
    if lines:
        return lines[0][:200]
    return None


def list_news_dates(output_dir: str = "news_output") -> List[Dict[str, str | bool]]:
    items: List[Dict[str, str | bool]] = []
    if not os.path.isdir(output_dir):
        return items
    for name in os.listdir(output_dir):
        iso = parse_date_from_filename(name)
        if not iso:
            continue
        path = os.path.join(output_dir, name)
        has_summary = False
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            if ("【摘要】" in txt) or ("## 今日热点总结" in txt):
                has_summary = True
        except Exception:
            pass
        items.append({"date": iso, "has_summary": has_summary})
    # 按日期倒序
    items.sort(key=lambda x: x["date"], reverse=True)
    return items


def run_generate_pipeline():
    """后台线程：执行抓取+处理+保存流程，并更新状态。"""
    try:
        set_status("crawling", 10, "正在爬取新闻数据...")

        # 读取环境配置
        from dotenv import load_dotenv
        load_dotenv()
        max_articles = int(os.getenv('MAX_ARTICLES', 10))
        api_key = os.getenv('API_KEY')
        api_url = os.getenv('API_URL', 'https://api.deepseek.com/v1/chat/completions')

        # 新闻源（与 main.py 保持一致）
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

        getter = NewsGetter(news_sources, max_articles)
        processor = NewsProcessor(api_key, api_url)
        gen = ReportGenerator()

        news_list = getter.get_news()
        if not news_list:
            raise RuntimeError("未获取到新闻内容")

        set_status("processing", 50, "正在AI处理新闻...")
        summary = processor.process_news(news_list)
        if summary:
            content = gen.create_report(summary, datetime.now())
        else:
            fallback = gen.create_fallback_summary(news_list)
            content = gen.create_report(fallback, datetime.now())

        ok = gen.save_report(content, datetime.now())
        if not ok:
            raise RuntimeError("保存报告失败")

        set_status("completed", 100, "新闻生成完成！")
    except Exception as e:
        set_status("failed", 100, "新闻生成失败", str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/news-list")
def api_news_list():
    return {"news_list": list_news_dates()}


@app.get("/api/news-detail")
def api_news_detail(date: str):
    path = find_news_file_by_date(date)
    if not path:
        raise HTTPException(status_code=404, detail="未找到该日期的新闻文件")
    try:
        with open(path, "r", encoding="utf-8") as f:
            md_text = f.read()
        summary = extract_summary_from_markdown(md_text) or ""
        return {"summary": summary, "content": md_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取新闻失败: {e}")


@app.post("/api/generate-news")
def api_generate_news():
    with gen_status_lock:
        if gen_status["status"] in ("crawling", "processing"):
            raise HTTPException(status_code=409, detail="已有生成任务在进行中")
        gen_status["status"] = "idle"
        gen_status["progress"] = 0
        gen_status["message"] = ""
        gen_status["error"] = ""

    t = threading.Thread(target=run_generate_pipeline, daemon=True)
    t.start()
    return {"success": True, "message": "新闻生成已触发"}


@app.get("/api/generate-status")
def api_generate_status():
    with gen_status_lock:
        return dict(gen_status)


# 挂载静态前端：访问 http://127.0.0.1:8000 即可打开可视化界面
static_dir = os.path.join(os.path.dirname(__file__), "HTML")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    # 若无前端目录，提供一个简单提示
    @app.get("/")
    def index_fallback():
        return {"message": "前端目录未找到，请创建 HTML/ 并包含 index.html"}
