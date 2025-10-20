"""
每日新闻自动爬取与总结系统（教学友好注释版）

本程序完成三件事：
1) 抓取新闻：访问新闻网站列表页，按 CSS 选择器提取标题/链接/时间/来源
2) AI 总结：将抓取到的新闻组织成 Prompt，调用你配置的 AI 服务生成【摘要】与【今日热点总结】
3) 生成报告：把结果写成 Markdown 文件，按“YYYY年MM月DD日每日新闻.md”命名

核心设计思路：
- 职责分离：
    - NewsGetter 负责“取数”（HTTP 请求 + 解析）
    - NewsProcessor 负责“加工”（构造 Prompt + 调用 AI 接口 + 解析响应）
    - ReportGenerator 负责“出数”（渲染 Markdown + 保存）
- 健壮性：
    - 请求随机延时、防简单反爬
    - 统一去重
    - API 调用失败时自动降级到“本地应急摘要”，保证报告结构不破坏
    - 详细日志 + debug_api_response.json 便于排障
- 可配置：
    - 通过 .env 控制 API_URL/API_KEY/API_MODEL/温度/最大 Token/重试次数/代理等
    - CSS 选择器可替换以适配不同站点结构

重要环境变量说明（.env）：
- API_KEY：调用 AI 服务的密钥（DeepSeek/OpenRouter/ModelScope 三选一）
- API_URL：OpenAI 兼容接口端点（建议以 /v1/chat/completions 结尾）
- API_MODEL：模型名（DeepSeek 官方：deepseek-chat；OpenRouter：deepseek/deepseek-chat-v3.1:free；ModelScope：deepseek-ai/DeepSeek-V3.1）
- API_TEMPERATURE：采样温度（0~1，越大越发散）
- API_MAX_TOKENS：最大生成 Token 数
- API_MAX_RETRIES：失败重试次数（不含首发起，共 max_retries+1 次）
- HTTP_PROXY / HTTPS_PROXY：如需通过代理访问外网可设置
- MAX_ARTICLES：最多处理的新闻条目数

新手阅读建议：先从 main() 的流程入手，再分别看三个类的实现；遇到 API 错误先查看 news.log 与 debug_api_response.json。
"""

import os
import time
import random
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

class NewsGetter:
    """新闻获取类

    负责：
    - 构造常见浏览器的请求头（User-Agent 等）并抓取 HTML
    - 使用 CSS 选择器解析列表页，提取新闻结构化字段
    - 统一去重，返回最多 max_articles 条新闻

    关键技术点：
    - requests 发起 HTTP GET
    - BeautifulSoup 解析 HTML
    - 通过 CSS Selector 定位节点（需随网站结构变化适配）
    """
    
    def __init__(self, news_sources: List[Dict], max_articles: int = 10):
        self.news_sources = news_sources
        self.max_articles = max_articles
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ]
    
    def get_page(self, url: str) -> Optional[str]:
        """抓取网页 HTML 内容。

        小技巧：
        - 设置常见浏览器的请求头，降低被简单反爬识别的概率
        - 每次请求加入 1~2 秒随机延时，避免频繁访问
        - 出错时记日志并返回 None（上层决定如何降级）
        """
        try:
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            time.sleep(random.uniform(1, 2))
            return response.text
        except Exception as e:
            logger.error(f"获取页面失败: {url}, 错误: {str(e)}")
            return None
    
    def parse_news(self, html: str, config: Dict) -> List[Dict]:
        """解析列表页 HTML，提取单条新闻的核心字段。

        参数说明：
        - html：列表页 HTML 文本
        - config：单个站点的解析配置（CSS 选择器、base_url 等）

        返回字段：title/link/publish_time/source

        注意：有些站点的链接是相对路径，这里会用 base_url 进行补全。
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select(config['item_selector'])
            logger.info(f"找到 {len(items)} 个匹配 '{config['item_selector']}' 的元素")
            
            if len(items) == 0:
                logger.warning(f"未找到匹配 '{config['item_selector']}' 的元素，请检查选择器是否正确")
                
            news_list = []
            
            for i, item in enumerate(items[:self.max_articles]):
                try:
                    title_elem = item.select_one(config['title_selector'])
                    if not title_elem:
                        logger.warning(f"第 {i+1} 个元素未找到标题选择器 '{config['title_selector']}'")
                        continue
                        
                    title = title_elem.get_text(strip=True)
                    
                    link_elem = item.select_one(config['link_selector'])
                    if not link_elem or 'href' not in link_elem.attrs:
                        logger.warning(f"第 {i+1} 个元素未找到链接选择器 '{config['link_selector']}' 或没有href属性")
                        continue
                        
                    link = link_elem['href']
                    
                    if link and not link.startswith('http'):
                        link = requests.compat.urljoin(config['base_url'], link)
                    
                    time_elem = item.select_one(config['time_selector']) if 'time_selector' in config else None
                    publish_time = time_elem.get_text(strip=True) if time_elem else ""
                    
                    source_elem = item.select_one(config['source_selector']) if 'source_selector' in config else None
                    source = source_elem.get_text(strip=True) if source_elem else config['name']
                    
                    news_list.append({
                        'title': title,
                        'link': link,
                        'publish_time': publish_time,
                        'source': source
                    })
                    
                    logger.info(f"成功解析新闻: {title}")
                except Exception as e:
                    logger.warning(f"解析新闻失败: {str(e)}")
                    continue
            
            return news_list
        except Exception as e:
            logger.error(f"解析页面失败: {str(e)}")
            return []
    
    def get_news(self) -> List[Dict]:
        """按配置的多个新闻源抓取并合并，最终返回去重后的新闻列表。"""
        logger.info("开始获取新闻...")
        all_news = []
        
        for source in self.news_sources:
            logger.info(f"正在获取: {source['name']} 从 {source['url']}")
            html = self.get_page(source['url'])
            if html:
                logger.info(f"成功获取 {source['name']} 页面，HTML长度: {len(html)}")
                # 保存HTML内容到文件以便调试
                with open(f"debug_{source['name'].replace(' ', '_')}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"已保存HTML到debug_{source['name'].replace(' ', '_')}.html文件")
                
                news = self.parse_news(html, source)
                all_news.extend(news)
                logger.info(f"从 {source['name']} 获取了 {len(news)} 条新闻")
            else:
                logger.error(f"无法获取 {source['name']} 的页面内容")
        
        # 去重
        unique_news = []
        seen = set()
        for news in all_news:
            key = (news['title'], news['link'])
            if key not in seen:
                seen.add(key)
                unique_news.append(news)
        
        logger.info(f"去重后共有 {len(unique_news)} 条新闻")
        result = unique_news[:self.max_articles]
        logger.info(f"最终返回 {len(result)} 条新闻")
        
        # 如果没有获取到新闻，添加测试数据
        if not result:
            logger.warning("未获取到任何新闻，添加测试数据")
            result = [
                {
                    'title': '测试新闻标题1',
                    'link': 'https://example.com/news/1',
                    'publish_time': '2023-01-01',
                    'source': '测试新闻源'
                },
                {
                    'title': '测试新闻标题2',
                    'link': 'https://example.com/news/2',
                    'publish_time': '2023-01-02',
                    'source': '测试新闻源'
                }
            ]
            logger.info(f"添加了 {len(result)} 条测试新闻")
        
        return result

class NewsProcessor:
    """新闻处理类

    负责：
    - 将新闻列表组织为高质量 Prompt（指令），提交给大模型
    - 兼容多家 OpenAI 样式 API（DeepSeek/OpenRouter/ModelScope）
    - 解析多种返回结构，提取生成的 Markdown 片段

    关键技术点：
    - 端点标准化：自动补齐 /v1/chat/completions，减少 404/Not Found
    - 模型名自适配：根据 API_URL 推断默认模型名，降低配置成本
    - 代理/重试：在弱网下更稳健
    - 调试文件：把原始响应写入 debug_api_response.json 便于排障
    """
    
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        # 允许用户传入基地址或完整路径，这里做标准化
        self.api_url = api_url.strip().rstrip('/') if api_url else ''

    def _normalize_endpoint(self) -> str:
        """根据传入的 api_url 自动补齐为 chat/completions 端点。
        支持如下几种形式：
        - https://api.deepseek.com/v1/chat/completions
        - https://api.deepseek.com/chat/completions
        - https://openrouter.ai/api/v1/chat/completions
        - https://openrouter.ai/api/v1 (自动补 /chat/completions)
        - ModelScope: https://api-inference.modelscope.cn/v1 （自动补 /chat/completions）
        - 其他提供商若路径不包含 chat/completions 则按原样返回
        """
        if not self.api_url:
            return ''
        url = self.api_url
        # 已经是完整 chat/completions
        if url.endswith('/chat/completions'):
            return url
        # 常见的 v1 或 api/v1 前缀
        if url.endswith('/v1') or url.endswith('/api/v1'):
            return url + '/chat/completions'
        # 深度求索官方也常见 /v1/chat/completions
        if 'api.deepseek.com' in url and url.endswith('/chat') is False:
            # 若给了根域或 /v1 根，则补全
            if url.rstrip('/').endswith('api.deepseek.com'):
                return url + '/v1/chat/completions'
        return url

    def _parse_api_response(self, data: Dict[str, Any]) -> Optional[str]:
        """尽可能兼容不同提供商的返回结构，优先 OpenAI 样式。"""
        if not isinstance(data, dict):
            return None
        # 明确识别 ModelScope 欢迎消息（非实际响应体）
        msg = data.get('message')
        if isinstance(msg, str) and 'ModelScope API-Inference' in msg:
            logger.error('检测到 ModelScope 欢迎消息：当前 API_URL 指向 ModelScope 推理服务且非 OpenAI 兼容，请改用 DeepSeek 官方或 OpenRouter，或按 ModelScope 文档调整请求。')
            return None
        # OpenAI / OpenRouter / DeepSeek（OpenAI 兼容）
        try:
            choices = data.get('choices')
            if isinstance(choices, list) and choices:
                choice0 = choices[0]
                # chat 模式：message.content
                if isinstance(choice0, dict):
                    msg = choice0.get('message') or {}
                    content = msg.get('content')
                    if content:
                        return content
                    # text 模式：text
                    if 'text' in choice0 and isinstance(choice0['text'], str):
                        return choice0['text']
        except Exception:
            pass

        # 其他可能字段（兜底）
        for key in ['output_text', 'result', 'content', 'data']:
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return None

    def _build_headers(self) -> Dict[str, str]:
        """构造请求头。

        - Authorization 采用 Bearer 规范
        - OpenRouter 建议附加 HTTP-Referer / X-Title（可选，用于统计来源）
        """
        http_referer = os.getenv('HTTP_REFERER', '')
        x_title = os.getenv('X_TITLE', '')
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        # OpenRouter 需要的可选标头（若配置则添加）
        if http_referer:
            headers['HTTP-Referer'] = http_referer
        if x_title:
            headers['X-Title'] = x_title
        return headers

    def create_prompt(self, news_list: List[Dict]) -> str:
        """把结构化新闻转成清晰的指令 Prompt。

        目标：
        - 限定格式（标题/摘要/链接 + 今日热点总结）
        - 约束摘要长度与语气（客观、简洁）
        - 降低模型“跑题”的概率
        """
        prompt = "请你作为新闻编辑，对以下新闻进行整理和总结：\n\n"
        
        for i, news in enumerate(news_list, 1):
            prompt += f"{i}. 【标题】{news['title']} - {news['source']} - {news['publish_time']}\n"
            prompt += f"   【原文链接】{news['link']}\n\n"
        
        prompt += """请请按照以下格式整理：
1. 每条新闻包含：
   - 【标题】- 来源 - 时间
   - 【摘要】（50字以内，提炼核心内容）
   - 【原文链接】<原文链接>
   
2. 最后添加"今日热点总结"（300字以内），总结当天的主要新闻热点和趋势。

要求：
- 摘要要客观中立，准确反映新闻内容
- 今日热点总结要具有概括性和洞察力
- 使用中文，语言简洁明了
"""
        
        return prompt
    
    def process_news(self, news_list: List[Dict]) -> Optional[str]:
        """调用大模型进行新闻总结，返回 Markdown 文本。

        流程：
        1) 组装 Prompt
        2) 选择模型与端点（支持自动推断）
        3) 附带代理/超时/重试策略发起请求
        4) 解析响应并落地调试文件
        5) 若解析失败则返回 None（上层会采用本地应急摘要）
        """
        if not news_list or not self.api_key:
            logger.warning("没有新闻可处理或API密钥未配置")
            return None
        
        logger.info("正在处理新闻...")
        
        try:
            prompt = self.create_prompt(news_list)
            
            # 从环境变量获取配置
            # 根据 API_URL 推断 provider，设置更合理的默认模型名
            api_url_env = os.getenv('API_URL', '').lower().strip()
            default_model = 'deepseek-chat'
            if 'api-inference.modelscope.cn' in api_url_env:
                # ModelScope 使用其 Model-Id
                default_model = 'deepseek-ai/DeepSeek-V3.1'
            elif 'openrouter.ai' in api_url_env:
                default_model = 'deepseek/deepseek-chat-v3.1:free'
            api_model = os.getenv('API_MODEL', default_model)

            headers = self._build_headers()
            endpoint = self._normalize_endpoint()
            if not endpoint:
                logger.error('API_URL 未正确配置，无法生成请求端点')
                return None

            payload = {
                'model': api_model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': float(os.getenv('API_TEMPERATURE', '0.7')),
                'max_tokens': int(os.getenv('API_MAX_TOKENS', '2000'))
            }

            # 代理支持（若用户配置了 HTTP(S)_PROXY 则 requests 会自动识别；这里允许通过自定义变量覆盖）
            proxies = {}
            http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            if http_proxy:
                proxies['http'] = http_proxy
            if https_proxy:
                proxies['https'] = https_proxy

            # 简单重试（网络/名称解析/临时 5xx）
            max_retries = int(os.getenv('API_MAX_RETRIES', '2'))
            last_err: Optional[Exception] = None
            for attempt in range(1, max_retries + 2):  # e.g. 2 重试 => 共 3 次
                try:
                    logger.info(f"调用API: {endpoint} (attempt {attempt}) 模型: {api_model}")
                    response = requests.post(endpoint, headers=headers, json=payload, timeout=30, proxies=proxies or None)
                    # 尝试解析错误信息
                    if response.status_code >= 400:
                        txt = ''
                        try:
                            txt = response.text[:500]
                        except Exception:
                            pass
                        logger.error(f"API返回错误: {response.status_code} {response.reason}; body: {txt}")
                        response.raise_for_status()
                    result = response.json()
                    # 保存调试文件以便问题复盘
                    try:
                        with open('debug_api_response.json', 'w', encoding='utf-8') as f:
                            import json as _json
                            _json.dump(result, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
                    # 如果是 ModelScope 域且返回为欢迎消息，直接提示并退出
                    if 'api-inference.modelscope.cn' in endpoint:
                        if isinstance(result, dict) and isinstance(result.get('message'), str) and 'ModelScope API-Inference' in result['message']:
                            logger.error('当前 API_URL 指向 ModelScope，但未按其文档使用正确的端点/参数；请改用 DeepSeek 官方或 OpenRouter 配置，或参考 ModelScope 文档。')
                            return None
                    content = self._parse_api_response(result)
                    if content and isinstance(content, str) and content.strip():
                        return content.strip()
                    # 若解析不到内容，记录一段返回体
                    logger.error("API响应未包含可用内容，将回退到原始列表。")
                    return None
                except Exception as e:
                    last_err = e
                    logger.error(f"调用API失败: {str(e)}")
                    # 轻微退避
                    time.sleep(1.0 * attempt)
                    continue
            # 多次失败
            if last_err:
                logger.error(f"处理新闻失败(重试后仍失败): {str(last_err)}")
            return None
        except Exception as e:
            logger.error(f"处理新闻失败: {str(e)}")
            return None

class ReportGenerator:
    """报告生成类

    负责：
    - 统一渲染 Markdown 标题
    - 在 API 失败时生成“本地应急摘要”
    - 将内容保存到 news_output 目录（自动建目录）

    小贴士：Markdown 用任何编辑器/笔记软件都可直接查看与分享。
    """
    
    @staticmethod
    def create_report(content: str, date: datetime) -> str:
        """把内容包上日期标题，形成完整的 Markdown 文本。"""
        title = f"# 每日新闻（{date.strftime('%Y年%m月%d日')}）\n\n"
        return title + content

    @staticmethod
    def create_fallback_summary(news_list: List[Dict]) -> str:
        """当外部 API 失败时的本地应急摘要，保证输出结构完整。"""
        lines = []
        for i, n in enumerate(news_list, 1):
            title = n.get('title', '').strip()
            src = n.get('source', '').strip()
            ts = n.get('publish_time', '').strip()
            link = n.get('link', '').strip()
            lines.append(f"{i}. 【标题】{title} - {src} - {ts}\n   【摘要】该条新闻暂无AI摘要（API未生效/限额/网络异常），请点击链接查看详情。\n   【原文链接】{link}\n")
        # 简单热点总结
        trends = '；'.join([n.get('title', '') for n in news_list[:5]])
        lines.append("\n## 今日热点总结\n")
        lines.append(f"受限于外部摘要服务，本日自动总结未生效。根据标题初步归纳热点：{trends}。建议稍后重试或检查 API 配置与网络代理设置。")
        return "\n".join(lines)
    
    @staticmethod
    def save_report(content: str, date: datetime, output_dir: str = 'news_output') -> bool:
        """把 Markdown 文本写入以日期命名的文件中。

        - 路径形如：news_output/YYYY年MM月DD日每日新闻.md
        - 若目录不存在会自动创建
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            filename = f"{date.strftime('%Y年%m月%d日')}每日新闻.md"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"报告已保存: {filepath}")
            return True
        except Exception as e:
            logger.error(f"保存报告失败: {str(e)}")
            return False

def main():
    """程序入口：组装配置 → 抓取新闻 → 调用 AI → 生成/保存报告。

    你可以：
    - 在下方 `news_sources` 中添加新的新闻源（修改 CSS 选择器）
    - 在 .env 控制 MAX_ARTICLES 等参数
    """
    try:
        # 新闻源配置
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
        
        # 配置
        max_articles = int(os.getenv('MAX_ARTICLES', 10))
        api_key = os.getenv('API_KEY')
        # 默认使用 DeepSeek 官方 v1 端点，避免与 OpenRouter 模型别名冲突
        api_url = os.getenv('API_URL', 'https://api.deepseek.com/v1/chat/completions')
        
        if not api_key:
            logger.error("请配置API_KEY")
            return
        
        # 创建实例
        news_getter = NewsGetter(news_sources, max_articles)
        news_processor = NewsProcessor(api_key, api_url)
        report_generator = ReportGenerator()
        
        # 获取新闻
        news_list = news_getter.get_news()
        if not news_list:
            logger.warning("未获取到新闻")
            return
        
        # 处理新闻
        summary = news_processor.process_news(news_list)
        
        # 生成报告
        if summary:
            report_content = report_generator.create_report(summary, datetime.now())
        else:
            # 使用本地应急摘要，保证结构完整
            fallback = report_generator.create_fallback_summary(news_list)
            report_content = report_generator.create_report(fallback, datetime.now())
        
        # 保存报告
        report_generator.save_report(report_content, datetime.now())
        
        logger.info("程序运行完成！")
        
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
