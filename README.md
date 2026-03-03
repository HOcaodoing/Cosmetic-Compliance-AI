# Cosmetic Compliance AI 🧴

> AI 驱动的化妆品成分合规性分析工具  
> *透明度不仅是营销——更是科学*

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red?logo=streamlit)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 📋 项目介绍

**Cosmetic Compliance AI** 是一款面向消费者和从业者的化妆品成分合规性分析工具。  
通过结合本地知识库（FDA 法规 / 中国化妆品安全技术规范）与 AI 技术，帮助用户：

- 🔍 **识别风险成分**：快速定位禁用/限用/潜在危害成分
- ✅ **双轨合规检查**：同步对照美国 FDA 和中国 GB 标准
- 💆 **肤质适用分析**：评估产品对不同肤质的友好程度
- 📊 **量化安全评分**：为每种成分和整体产品提供直观评分

---

## ✨ 功能特点

| 功能 | 描述 |
|------|------|
| 🔍 产品查询 | 输入品牌+产品名，自动获取成分列表 |
| 📝 成分解析 | 支持直接粘贴 INCI 或中文成分表 |
| 🧪 安全性评分 | 基于 EWG 标准和本地数据库的 1-10 分评分 |
| 📋 合规性检测 | FDA & 中国法规双轨检测 |
| 💆 肤质匹配 | 7 种肤质适用性评分 |
| 💊 专业建议 | 个性化护肤建议 |
| ⚡ 智能缓存 | JSON + SQLite 双层缓存，重复查询秒级响应 |
| 📥 报告导出 | 支持导出 JSON 格式完整分析报告 |

---

## 🗂️ 项目结构

```
cosmetic-compliance-ai/
├── app.py              # Streamlit 主应用（UI + 主逻辑）
├── scraper.py          # 网络爬虫模块（多数据源 + 降级策略）
├── cache.py            # 缓存管理（JSON 文件 + SQLite 历史）
├── analyzer.py         # 核心分析引擎（合规性 + 安全评分）
├── requirements.txt    # 项目依赖
├── .env.example        # 环境变量模板
├── data/
│   ├── ingredients_db.json     # 成分安全性数据库（25+ 种常见成分）
│   ├── fda_restricted.json     # FDA 禁限用成分列表
│   ├── gb_restricted.json      # 中国法规禁限用成分列表
│   └── cache/                  # 运行时缓存目录（自动创建）
├── tests/
│   ├── test_analyzer.py        # 分析模块单元测试
│   ├── test_scraper.py         # 爬虫模块测试
│   └── test_cache.py           # 缓存模块测试
└── .github/
    └── workflows/
        └── ci.yml              # GitHub Actions CI 配置
```

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/cosmetic-compliance-ai.git
cd cosmetic-compliance-ai
```

### 2. 安装依赖

```bash
# 推荐使用虚拟环境
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. 运行应用

```bash
streamlit run app.py
```

浏览器访问 `http://localhost:8501` 即可使用。

---

## 🔧 环境变量配置（可选）

复制 `.env.example` 并重命名为 `.env`：

```bash
cp .env.example .env
```

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key（启用 LLM 深度分析） | 空（使用本地分析） |
| `CACHE_EXPIRY_HOURS` | 缓存有效期（小时） | 24 |
| `LOG_LEVEL` | 日志级别 | INFO |

---

## 🧪 运行测试

```bash
# 安装测试依赖
pip install pytest

# 运行所有测试
pytest tests/ -v

# 查看测试覆盖率
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

---

## 🏗️ 技术栈

| 层次 | 技术 |
|------|------|
| **前端** | Streamlit 1.32+ |
| **后端** | Python 3.10+ |
| **爬虫** | Requests + BeautifulSoup4 |
| **数据处理** | Pandas |
| **数据存储** | JSON 文件缓存 + SQLite |
| **AI 分析** | 本地规则引擎（可选接入 OpenAI GPT） |
| **CI/CD** | GitHub Actions |

---

## 📊 数据来源

- **成分安全数据**：基于 EWG Skin Deep 数据库整理
- **FDA 法规**：21 CFR Part 700 系列法规
- **中国标准**：《化妆品安全技术规范》（2015年版）

> ⚠️ 免责声明：本工具仅供参考，不构成医疗建议。实际产品安全性请以官方检测报告为准。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'feat: add your feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 发起 Pull Request

### 扩展建议

- [ ] 接入更多数据源（OpenFDA API、EWG API）
- [ ] 实现 OCR 图片识别成分表
- [ ] 集成 OpenAI GPT 进行自然语言深度分析
- [ ] 添加更多成分数据（目标 500+ 种）
- [ ] 支持成分比较功能
- [ ] 多语言支持（英文界面）

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 👨‍💻 作者

**Cosmetic Compliance AI Team**  
展示 Full-stack 开发 + 化工专业知识 + AI 技术集成能力

*如有问题，欢迎通过 [Issues](https://github.com/YOUR_USERNAME/cosmetic-compliance-ai/issues) 反馈。*

---

## 🚀 Live Demo

Run locally:
```bash
git clone https://github.com/HOcaodoing/Cosmetic-Compliance-AI.git
cd Cosmetic-Compliance-AI
pip install -r requirements.txt
streamlit run app.py
```
