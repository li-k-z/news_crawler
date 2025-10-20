// 全局变量
let newsList = [];
let currentDate = null;
let isGenerating = false;
let generateInterval = null;

// DOM元素
const pageLoader = document.getElementById('page-loader');
const themeToggle = document.getElementById('theme-toggle');
const dateList = document.getElementById('date-list');
const welcomePage = document.getElementById('welcome-page');
const newsContent = document.getElementById('news-content');
const newsDateTitle = document.getElementById('news-date-title');
const newsSummary = document.getElementById('news-summary');
const markdownContent = document.getElementById('markdown-content');
const generateNewsBtn = document.getElementById('generate-news-btn');
const refreshNewsBtn = document.getElementById('refresh-news-btn');
const generateStatus = document.getElementById('generate-status');
const statusMessage = document.getElementById('status-message');
const progressBar = document.getElementById('progress-bar');
const errorMessage = document.getElementById('error-message');
const errorDetails = document.getElementById('error-details');
const lastUpdated = document.getElementById('last-updated');
const scrollTopBtn = document.getElementById('scroll-top-btn');
const collapseAllBtn = document.getElementById('collapse-all');
const lightTheme = document.getElementById('light-theme');
const darkTheme = document.getElementById('dark-theme');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
  // 检查主题偏好
  checkThemePreference();
  
  // 初始化页面
  initializePage();
  
  // 绑定事件
  bindEvents();
});

// 检查主题偏好
function checkThemePreference() {
  if (localStorage.getItem('theme') === 'dark' || 
      (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
    lightTheme.disabled = true;
    darkTheme.disabled = false;
  } else {
    document.documentElement.classList.remove('dark');
    lightTheme.disabled = false;
    darkTheme.disabled = true;
  }
}

// 初始化页面
function initializePage() {
  // 简短加载动画后拉取真实数据
  setTimeout(() => {
    pageLoader.classList.add('hidden');
    fetchNewsList();
    updateLastUpdated();
  }, 500);
}

// 绑定事件
function bindEvents() {
  // 主题切换
  themeToggle.addEventListener('click', toggleTheme);
  
  // 生成新闻按钮
  generateNewsBtn.addEventListener('click', generateTodayNews);
  
  // 刷新新闻按钮
  refreshNewsBtn.addEventListener('click', () => {
    if (currentDate) {
      fetchNewsDetail(currentDate);
    }
  });
  
  // 滚动到顶部按钮
  scrollTopBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  
  // 全部折叠按钮
  collapseAllBtn.addEventListener('click', collapseAllMonths);
  
  // 窗口滚动事件
  window.addEventListener('scroll', () => {
    if (window.scrollY > 300) {
      scrollTopBtn.classList.remove('hidden');
    } else {
      scrollTopBtn.classList.add('hidden');
    }
  });
}

// 切换主题
function toggleTheme() {
  if (document.documentElement.classList.contains('dark')) {
    document.documentElement.classList.remove('dark');
    localStorage.setItem('theme', 'light');
    lightTheme.disabled = false;
    darkTheme.disabled = true;
  } else {
    document.documentElement.classList.add('dark');
    localStorage.setItem('theme', 'dark');
    lightTheme.disabled = true;
    darkTheme.disabled = false;
  }
  
  // 如果当前有新闻内容，重新渲染以适应新主题
  if (currentDate && markdownContent.innerHTML) {
    const tempContent = markdownContent.innerHTML;
    markdownContent.innerHTML = tempContent;
    hljs.highlightAll();
  }
}

// 获取新闻列表
async function fetchNewsList() {
  try {
    const res = await fetch('/api/news-list');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    newsList = data.news_list || [];
    renderDateList();
  } catch (err) {
    showError('获取新闻列表失败', err.message || String(err));
  }
}

// 渲染日期列表
function renderDateList() {
  if (!newsList.length) {
    dateList.innerHTML = '<p class="text-gray-500 dark:text-gray-400 text-center py-4">暂无新闻数据</p>';
    return;
  }
  
  // 按月份分组
  const groupedByMonth = {};
  
  newsList.forEach(news => {
    const date = new Date(news.date);
    const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    
    if (!groupedByMonth[monthKey]) {
      groupedByMonth[monthKey] = [];
    }
    
    groupedByMonth[monthKey].push(news);
  });
  
  // 清空日期列表
  dateList.innerHTML = '';
  
  // 渲染分组后的日期列表
  Object.keys(groupedByMonth).sort((a, b) => b.localeCompare(a)).forEach(monthKey => {
    const [year, month] = monthKey.split('-');
    const monthName = new Date(year, month - 1).toLocaleString('zh-CN', { month: 'long' });
    const monthNews = groupedByMonth[monthKey];
    
    // 创建月份分组
    const monthGroup = document.createElement('div');
    monthGroup.className = 'mb-4';
    monthGroup.innerHTML = `
      <div class="flex justify-between items-center cursor-pointer month-header">
        <h3 class="font-medium text-gray-700 dark:text-gray-300">${year}年 ${monthName}</h3>
        <i class="fa fa-chevron-down text-xs text-gray-500 dark:text-gray-400 transition-transform"></i>
      </div>
      <div class="month-content mt-1 space-y-1">
        ${monthNews.map(news => `
          <div class="date-item pl-3 py-2 rounded cursor-pointer ${currentDate === news.date ? 'active' : ''}" 
               data-date="${news.date}">
            <div class="flex justify-between items-center">
              <span>${formatDate(news.date)}</span>
              ${news.has_summary ? '<span class="text-xs bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 px-2 py-0.5 rounded">已总结</span>' : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `;
    
    dateList.appendChild(monthGroup);
    
    // 添加月份展开/折叠事件
    const monthHeader = monthGroup.querySelector('.month-header');
    const monthContent = monthGroup.querySelector('.month-content');
    const chevron = monthGroup.querySelector('.fa-chevron-down');
    
    monthHeader.addEventListener('click', () => {
      monthContent.classList.toggle('hidden');
      chevron.classList.toggle('rotate-180');
    });
    
    // 默认展开第一个月
    if (Object.keys(groupedByMonth).indexOf(monthKey) === 0) {
      monthContent.classList.remove('hidden');
    } else {
      monthContent.classList.add('hidden');
    }
    
    // 添加日期点击事件
    monthNews.forEach(news => {
      const dateItem = monthGroup.querySelector(`.date-item[data-date="${news.date}"]`);
      if (dateItem) {
        dateItem.addEventListener('click', () => {
          // 移除其他日期的激活状态
          document.querySelectorAll('.date-item').forEach(item => {
            item.classList.remove('active');
          });
          
          // 添加当前日期的激活状态
          dateItem.classList.add('active');
          
          // 获取并显示新闻详情
          currentDate = news.date;
          fetchNewsDetail(news.date);
        });
      }
    });
  });
}

// 获取新闻详情
async function fetchNewsDetail(date) {
  // 显示新闻内容区域，隐藏欢迎页面
  newsContent.classList.remove('hidden');
  welcomePage.classList.add('hidden');
  
  // 设置新闻日期标题
  const formattedDate = formatDate(date);
  newsDateTitle.textContent = `${formattedDate} 新闻`;
  
  // 显示加载状态
  showLoading();
  
  try {
    const res = await fetch(`/api/news-detail?date=${encodeURIComponent(date)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    newsSummary.textContent = data.summary || '暂无摘要';
    markdownContent.innerHTML = marked.parse(data.content || '# 暂无新闻内容');
    hljs.highlightAll();
    hideLoading();
  } catch (err) {
    showError('获取新闻详情失败', err.message || String(err));
    hideLoading();
  }
}

// 生成今日新闻
async function generateTodayNews() {
  if (isGenerating) return;
  
  isGenerating = true;
  
  // 禁用生成按钮
  generateNewsBtn.disabled = true;
  generateNewsBtn.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i> 生成中...';
  
  // 显示生成状态区域
  generateStatus.classList.remove('hidden');
  statusMessage.textContent = '正在爬取新闻数据...';
  progressBar.style.width = '0%';
  
  try {
    const res = await fetch('/api/generate-news', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await res.json();
    startGenerateStatusPolling();
  } catch (err) {
    showError('触发新闻生成失败', err.message || String(err));
    resetGenerateButton();
    generateStatus.classList.add('hidden');
    isGenerating = false;
  }
}

// 开始轮询生成状态
function startGenerateStatusPolling() {
  let progress = 0;
  
  generateInterval = setInterval(() => {
    fetch('/api/generate-status')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        progress = data.progress || 0;
        progressBar.style.width = `${progress}%`;
        
        // 更新状态消息
        switch (data.status) {
          case 'crawling':
            statusMessage.textContent = '正在爬取新闻数据...';
            break;
          case 'processing':
            statusMessage.textContent = '正在AI处理新闻...';
            break;
          case 'completed':
            statusMessage.textContent = '新闻生成完成！';
            progressBar.style.width = '100%';
            
            // 清除轮询
            clearInterval(generateInterval);
            
            // 恢复按钮状态
            resetGenerateButton();
            
            // 隐藏生成状态区域
            setTimeout(() => {
              generateStatus.classList.add('hidden');
            }, 1000);
            
            // 刷新新闻列表
            fetchNewsList();
            
            // 获取并显示今日新闻
            const today = new Date().toISOString().split('T')[0];
            currentDate = today;
            fetchNewsDetail(today);
            
            isGenerating = false;
            break;
          case 'failed':
            statusMessage.textContent = '新闻生成失败';
            
            // 显示错误信息
            showError('新闻生成失败', data.error || '未知错误');
            
            // 清除轮询
            clearInterval(generateInterval);
            
            // 恢复按钮状态
            resetGenerateButton();
            
            // 隐藏生成状态区域
            setTimeout(() => {
              generateStatus.classList.add('hidden');
            }, 1000);
            
            isGenerating = false;
            break;
          default:
            statusMessage.textContent = `正在处理中... ${progress}%`;
        }
      })
      .catch(err => {
        showError('获取生成状态失败', err.message || String(err));
        clearInterval(generateInterval);
        resetGenerateButton();
        generateStatus.classList.add('hidden');
        isGenerating = false;
      });
  }, 1000);
}

// 恢复生成按钮状态
function resetGenerateButton() {
  generateNewsBtn.disabled = false;
  generateNewsBtn.innerHTML = '<i class="fa fa-refresh mr-2"></i> 生成今日新闻';
}

// 显示加载状态
function showLoading() {
  markdownContent.innerHTML = `
    <div class="flex flex-col items-center justify-center py-12">
      <div class="loading-spinner mb-4"></div>
      <p class="text-gray-500 dark:text-gray-400">加载中...</p>
    </div>
  `;
}

// 隐藏加载状态
function hideLoading() {
  // 已在fetchNewsDetail中处理
}

// 显示错误信息
function showError(title, message) {
  errorDetails.textContent = message;
  errorMessage.classList.remove('hidden');
  
  // 3秒后自动隐藏错误信息
  setTimeout(() => {
    errorMessage.classList.add('hidden');
  }, 5000);
}

// 更新最后更新时间
function updateLastUpdated() {
  const now = new Date();
  lastUpdated.textContent = `最后更新: ${formatDateTime(now)}`;
}

// 全部折叠
function collapseAllMonths() {
  document.querySelectorAll('.month-content').forEach(content => {
    content.classList.add('hidden');
  });
  
  document.querySelectorAll('.month-header .fa-chevron-down').forEach(chevron => {
    chevron.classList.remove('rotate-180');
  });
}

// 格式化日期（YYYY-MM-DD 转 MM月DD日）
function formatDate(dateString) {
  const date = new Date(dateString);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

// 格式化日期时间
function formatDateTime(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

// 已移除模拟API，前端直接请求后端真实接口
