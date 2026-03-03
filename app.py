"""
app.py - Streamlit 主应用（Step 2 全面升级版）
Cosmetic Compliance AI

新增：
  - 数据库初始化 & 状态展示
  - LLM AI 报告标签页（含本地规则引擎兜底）
  - 组合风险专区展示
  - 过敏原识别板块
  - 风险等级颜色系统（Low/Medium/High/Critical）
  - 数据库知识库搜索页
  - 完整侧边栏升级
"""

import json
import streamlit as st
from datetime import datetime
from pathlib import Path

from database import init_database, get_db_stats, get_query_history_db, search_ingredients, get_banned_ingredients
from scraper import web_scraper, parse_ingredient_text, validate_ingredients
from cache import check_cache, cache_result, generate_product_id, get_cache_stats, clear_cache
from analyzer import analyze_product, report_to_dict
from llm_report import generate_full_report, generate_quick_summary

# ─────────────────────────────────────────────
# 页面配置
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI 化妆品成分合规性分析助手",
    page_icon="🧴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# 数据库初始化（仅首次运行）
# ─────────────────────────────────────────────
@st.cache_resource
def _init_db():
    """Streamlit 缓存的数据库初始化（只执行一次）"""
    init_database()
    return True

_init_db()

# ─────────────────────────────────────────────
# 全局样式
# ─────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --primary: #FF6B9D;
    --safe: #28a745;
    --caution: #ffc107;
    --concern: #fd7e14;
    --high: #dc3545;
    --critical: #6f1c1c;
    --unknown: #6c757d;
}

/* 卡片 */
.metric-card {
    background: linear-gradient(135deg, #fff5f8, #fff);
    border: 1px solid #ffe0ec;
    border-radius: 12px;
    padding: 18px 22px;
    margin: 6px 0;
    box-shadow: 0 2px 8px rgba(255,107,157,0.07);
}

/* 成分标签 */
.ingredient-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 13px;
    margin: 3px;
    font-weight: 500;
}
.badge-safe     { background:#d4edda; color:#155724; }
.badge-caution  { background:#fff3cd; color:#856404; }
.badge-concern  { background:#fde8d8; color:#7d3109; }
.badge-high     { background:#f8d7da; color:#721c24; }
.badge-critical { background:#4a0000; color:#fff; }
.badge-unknown  { background:#e9ecef; color:#495057; }

/* 风险标签 */
.risk-low      { color:#28a745; font-weight:600; }
.risk-medium   { color:#ffc107; font-weight:600; }
.risk-high     { color:#dc3545; font-weight:600; }
.risk-critical { color:#6f1c1c; font-weight:700; }

/* 组合风险区块 */
.combo-risk-card {
    border-left: 4px solid #fd7e14;
    background: #fff8f0;
    padding: 12px 16px;
    border-radius: 8px;
    margin: 8px 0;
}

/* 渐变标题 */
.gradient-title {
    background: linear-gradient(90deg, #FF6B9D, #C770CF);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.1em;
    font-weight: 800;
    line-height: 1.2;
}

/* LLM报告区域 */
.llm-report {
    background: #f8f9ff;
    border: 1px solid #d0d5ff;
    border-radius: 12px;
    padding: 20px 24px;
    line-height: 1.8;
}

/* 评分进度条 */
.score-bar-wrap { width: 100%; background: #e9ecef; border-radius: 6px; height: 10px; }
.score-bar-fill { height: 10px; border-radius: 6px; transition: width 0.5s; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 辅助常量 & 函数
# ─────────────────────────────────────────────

SAFETY_EMOJI = {
    "safe":             ("🟢", "安全",    "#28a745"),
    "caution":          ("🟡", "需关注",  "#ffc107"),
    "moderate_concern": ("🟠", "中度关注","#fd7e14"),
    "concern":          ("🔴", "高风险",  "#dc3545"),
    "prohibited":       ("⛔", "禁用",    "#6f1c1c"),
    "unknown":          ("⚪", "未知",    "#6c757d"),
}

RISK_COLORS = {
    "Low":      "#28a745",
    "Medium":   "#ffc107",
    "High":     "#dc3545",
    "Critical": "#6f1c1c",
}

COMPLIANCE_ICON = {
    "compliant":  "✅ 合规",
    "restricted": "⚠️ 含限制成分",
    "prohibited": "🚫 含禁用成分",
}


def score_html(score: float, max_score: float = 10) -> str:
    pct = int(score / max_score * 100)
    c = "#28a745" if score >= 8 else ("#ffc107" if score >= 6 else "#dc3545")
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar-fill" style="width:{pct}%;background:{c};"></div></div>'
        f'<small style="color:{c};font-weight:600;">{score}/10</small>'
    )


def get_badge_class(level: str) -> str:
    return {
        "safe":             "badge-safe",
        "caution":          "badge-caution",
        "moderate_concern": "badge-concern",
        "concern":          "badge-high",
        "prohibited":       "badge-critical",
    }.get(level, "badge-unknown")


def risk_badge_html(risk_level: str) -> str:
    color_cls = {
        "Low": "risk-low", "Medium": "risk-medium",
        "High": "risk-high", "Critical": "risk-critical"
    }.get(risk_level, "risk-medium")
    icon = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Critical": "⛔"}.get(risk_level, "🟡")
    return f'<span class="{color_cls}">{icon} {risk_level}</span>'


# ─────────────────────────────────────────────
# 侧边栏（升级版）
# ─────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## 🧴 导航")
        page = st.radio(
            "选择页面",
            ["🔍 成分分析", "📚 知识库搜索", "📊 数据库状态"],
            label_visibility="collapsed"
        )
        st.markdown("---")

        # 数据库快速状态
        db_stats = get_db_stats()
        if db_stats.get("initialized"):
            st.markdown("### 🗄️ 数据库状态")
            c1, c2 = st.columns(2)
            c1.metric("成分数", db_stats.get("ingredients_count", 0))
            c2.metric("查询历史", db_stats.get("history_count", 0))
        st.markdown("---")

        # 缓存
        st.markdown("### 📦 缓存")
        cache_stats = get_cache_stats()
        c1, c2 = st.columns(2)
        c1.metric("有效缓存", cache_stats["valid_entries"])
        c2.metric("大小KB", cache_stats["cache_size_kb"])
        if st.button("🗑️ 清除缓存", use_container_width=True):
            n = clear_cache()
            st.success(f"已清除 {n} 条")
        st.markdown("---")

        # 查询历史（数据库）
        st.markdown("### 🕐 最近查询")
        try:
            history = get_query_history_db(limit=6)
        except Exception:
            history = []
        if history:
            for h in history:
                t = h.get("queried_at", "")[:16]
                st.markdown(f"- `{h.get('brand','')}` · {h.get('product','')} <small>{t}</small>",
                            unsafe_allow_html=True)
        else:
            st.caption("暂无查询历史")
        st.markdown("---")

        # LLM 配置
        st.markdown("### 🤖 LLM 配置")
        api_key = st.text_input("OpenAI API Key（可选）",
                                type="password",
                                placeholder="sk-...",
                                help="填入后将使用 GPT 生成深度分析报告")
        if api_key:
            import os
            os.environ["OPENAI_API_KEY"] = api_key
            st.success("✅ API Key 已设置")
        else:
            st.caption("📌 未设置 → 使用本地规则引擎")
        st.markdown("---")

        st.markdown("### 📖 关于")
        st.markdown("""
**Cosmetic Compliance AI** v2.0  
数据来源：
- 🇺🇸 FDA 21 CFR  
- 🇨🇳 化妆品安全技术规范(2015)  
- 🇪🇺 EU Reg. 1223/2009  
- 📊 EWG Skin Deep

[GitHub](https://github.com/HOcaodoing/Cosmetic-Compliance-AI)
        """)

    return page


# ─────────────────────────────────────────────
# 成分分析页：输入区
# ─────────────────────────────────────────────

def render_input_section() -> dict | None:
    st.markdown('<p class="gradient-title">AI 化妆品成分合规性分析助手</p>', unsafe_allow_html=True)
    st.markdown("##### *透明度不仅是营销——更是科学 | Step 2: 深度分析 + AI 报告生成*")

    with st.expander("💡 新功能介绍（Step 2）", expanded=False):
        col1, col2, col3 = st.columns(3)
        col1.markdown("**🗄️ SQLite 数据库**\n- 四张核心表\n- 产品+成分持久化\n- 法规标准关联")
        col2.markdown("**⚗️ 组合风险检测**\n- 苯甲酸钠×维C → 苯\n- 视黄醇×酸类刺激\n- 10+ 组合风险规则")
        col3.markdown("**🤖 AI 报告生成**\n- LLM Prompt 引擎\n- 本地规则引擎兜底\n- 替代品推荐")

    st.markdown("---")

    input_method = st.radio(
        "**选择产品信息输入方式：**",
        ["🔍 手动输入品牌和产品名", "📝 直接粘贴成分表", "📋 示例演示"],
        horizontal=True,
    )

    product_info = {}

    if "手动输入" in input_method:
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("🏷️ 品牌名称", placeholder="例如：欧莱雅 / L'Oréal")
        with col2:
            product = st.text_input("📦 产品名称", placeholder="例如：小黑瓶精华")
        if brand and product:
            product_info = {"brand": brand, "product": product, "input_method": "manual", "ingredients": None}

    elif "直接粘贴" in input_method:
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("🏷️ 品牌名称（选填）", placeholder="例如：自有品牌")
        with col2:
            product = st.text_input("📦 产品名称（选填）", placeholder="例如：保湿面霜")
        raw_text = st.text_area(
            "📋 粘贴成分表（INCI / 中文均可，逗号/换行分隔）",
            height=140,
            placeholder="例如：Water, Glycerin, Niacinamide, Sodium Benzoate, Ascorbic Acid..."
        )
        if raw_text.strip():
            parsed = parse_ingredient_text(raw_text)
            v = validate_ingredients(parsed)
            if v["valid"]:
                st.success(f"✅ {v['message']}")
                product_info = {
                    "brand": brand or "未知品牌",
                    "product": product or "自定义产品",
                    "input_method": "paste",
                    "ingredients": parsed,
                }
            else:
                st.error(f"❌ {v['message']}")

    else:
        demo_options = {
            "珀莱雅 · 双抗精华（含维C×苯甲酸钠组合风险）": ("珀莱雅", "双抗精华"),
            "欧莱雅 · 小黑瓶精华": ("欧莱雅", "小黑瓶精华"),
            "完美日记 · 粉底液（含Paraben）": ("完美日记", "粉底液"),
            "L'Oréal · Shampoo（含香精+Paraben）": ("loreal", "shampoo"),
            "高风险演示产品（含Triclosan等）": ("demo", "high_risk_product"),
            "苯甲酸钠+维C 组合风险演示": ("demo", "benzene_risk"),
        }
        choice = st.selectbox("选择演示产品", list(demo_options.keys()))
        brand, product = demo_options[choice]
        product_info = {"brand": brand, "product": product, "input_method": "manual", "ingredients": None}
        st.info(f"📌 已选择示例：**{choice}**")

    return product_info if product_info else None


# ─────────────────────────────────────────────
# 报告渲染（升级版）
# ─────────────────────────────────────────────

def render_overview(report: dict):
    score = report["overall_safety_score"]
    level = report["overall_safety_level"]
    risk  = report.get("overall_risk_level", "Medium")
    emoji, label, color = SAFETY_EMOJI.get(level, ("⚪", "未知", "#6c757d"))
    risk_color = RISK_COLORS.get(risk, "#6c757d")

    st.markdown("### 📊 分析总览")
    cols = st.columns(5)

    with cols[0]:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:13px;color:#888;">综合安全评分</div>
            <div style="font-size:2em;font-weight:800;color:{color};">{score}</div>
            {score_html(score)}
        </div>""", unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:13px;color:#888;">安全等级</div>
            <div style="font-size:2em;">{emoji}</div>
            <div style="font-size:13px;font-weight:600;color:{color};">{label}</div>
        </div>""", unsafe_allow_html=True)

    with cols[2]:
        flag_count = len(report.get("flagged_ingredients", []))
        flag_color = "#dc3545" if flag_count > 0 else "#28a745"
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:13px;color:#888;">整体风险等级</div>
            <div style="font-size:1.6em;font-weight:800;color:{risk_color};">{risk}</div>
            <div style="font-size:12px;color:#888;">{flag_count} 种成分需关注</div>
        </div>""", unsafe_allow_html=True)

    with cols[3]:
        allergen_count = len(report.get("allergens_found", []))
        combo_count    = len(report.get("combination_risks", []))
        al_color = "#dc3545" if allergen_count > 0 else "#28a745"
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:13px;color:#888;">过敏原 / 组合风险</div>
            <div style="font-size:1.8em;font-weight:800;color:{al_color};">{allergen_count}</div>
            <div style="font-size:12px;color:#888;">⚗️ 组合风险 {combo_count} 项</div>
        </div>""", unsafe_allow_html=True)

    with cols[4]:
        fda_c = report.get("fda_compliance", "compliant")
        gb_c  = report.get("gb_compliance", "compliant")
        st.markdown(f"""<div class="metric-card">
            <div style="font-size:13px;color:#888;">合规状态</div>
            <div style="font-size:12px;margin-top:6px;">🇺🇸 {COMPLIANCE_ICON.get(fda_c, fda_c)}</div>
            <div style="font-size:12px;margin-top:4px;">🇨🇳 {COMPLIANCE_ICON.get(gb_c, gb_c)}</div>
        </div>""", unsafe_allow_html=True)


def render_combination_risks(report: dict):
    combo_risks = report.get("combination_risks", [])
    if not combo_risks:
        st.success("✅ 未检测到成分组合风险")
        return

    st.markdown(f"### ⚗️ 成分组合风险（{len(combo_risks)} 项）")
    severity_colors = {"Critical": "#6f1c1c", "High": "#dc3545", "Medium": "#fd7e14", "Low": "#ffc107"}
    for cr in combo_risks:
        sev = cr.get("severity", "Medium")
        c   = severity_colors.get(sev, "#fd7e14")
        st.markdown(f"""
        <div class="combo-risk-card" style="border-left-color:{c};">
            <strong style="color:{c};">⚗️ {cr['ingredient_a']} + {cr['ingredient_b']}</strong>
            <span style="float:right;background:{c};color:#fff;padding:2px 8px;
                         border-radius:12px;font-size:12px;">{sev}</span><br/>
            <small style="color:#555;">{cr['risk_description']}</small>
        </div>
        """, unsafe_allow_html=True)


def render_allergens(report: dict):
    allergens = report.get("allergens_found", [])
    if not allergens:
        st.success("✅ 未检测到已知致敏原")
        return

    st.markdown(f"### 🌸 过敏原清单（{len(allergens)} 种）")
    st.warning("过敏体质人群请注意！建议首次使用前进行 48h 贴肤测试（耳后或内腕）。")
    badges = " ".join(
        f"<span class='ingredient-badge badge-high'>⚠️ {a}</span>"
        for a in allergens
    )
    st.markdown(badges, unsafe_allow_html=True)


def render_flagged_ingredients(report: dict):
    flagged = report.get("flagged_ingredients", [])
    if not flagged:
        st.success("🎉 未发现需要特别关注的风险成分！")
        return

    st.markdown(f"### ⚠️ 需关注成分（{len(flagged)} 种）")
    for item in flagged:
        level = item.get("safety_level", "unknown")
        emoji = SAFETY_EMOJI.get(level, ("⚪",))[0]
        score_i = item.get("safety_score", "?")
        risk_l = item.get("risk_level", "Medium")

        with st.expander(
            f"{emoji} **{item['inci_name']}** "
            f"{'（' + item.get('cn_name','') + '）' if item.get('cn_name') else ''} "
            f"— 评分 {score_i}/10 | 风险: {risk_l}",
            expanded=item.get("risk_level") in ("High", "Critical")
        ):
            col1, col2 = st.columns([2, 1])
            with col1:
                if item.get("description"):
                    st.markdown(f"📌 **说明：** {item['description']}")
                if item.get("function"):
                    st.markdown(f"🔬 **功能：** {', '.join(item['function'])}")
                if item.get("concerns"):
                    st.markdown("⚠️ **注意事项：**")
                    for c in item["concerns"]:
                        st.markdown(f"  - {c}")
                if item.get("combination_warnings"):
                    st.markdown("⚗️ **组合风险：**")
                    for cw in item["combination_warnings"]:
                        st.markdown(f"  - 与 `{cw.get('partner','')}` 同用：{cw.get('risk','')}")
            with col2:
                st.markdown(f"**FDA：** `{item.get('fda_status','—')}`")
                st.markdown(f"**GB：** `{item.get('gb_status','—')}`")
                st.markdown(f"**风险：** {risk_l}")
                if item.get("max_concentration") and item["max_concentration"] != "Not specified":
                    st.markdown(f"**限量：** {item['max_concentration']}")
                if item.get("allergen"):
                    st.markdown("🌸 **已知致敏原**")
                st.markdown(score_html(score_i if isinstance(score_i, (int, float)) else 5), unsafe_allow_html=True)


def render_all_ingredients(report: dict):
    analyses = report.get("ingredient_analyses", [])
    st.markdown(f"### 🔬 成分全表（{len(analyses)} 种）")

    search = st.text_input("🔍 搜索成分", placeholder="输入 INCI 或中文名...", key="ing_search_v2")
    if search:
        analyses = [a for a in analyses
                    if search.lower() in a["inci_name"].lower()
                    or search.lower() in a.get("cn_name", "").lower()]

    cols = st.columns([2.5, 1.8, 1.2, 1.5, 1.5, 2])
    for col, h in zip(cols, ["INCI名称", "中文名", "评分", "风险", "功能", "主要关注"]):
        col.markdown(f"**{h}**")
    st.markdown("---")

    for item in analyses:
        level = item.get("safety_level", "unknown")
        emoji = SAFETY_EMOJI.get(level, ("⚪",))[0]
        risk_l = item.get("risk_level", "Low")
        badge = get_badge_class(level)

        row = st.columns([2.5, 1.8, 1.2, 1.5, 1.5, 2])
        row[0].markdown(f"**{item['inci_name']}**" + (" 🌸" if item.get("allergen") else ""))
        row[1].markdown(item.get("cn_name") or "-")
        row[2].markdown(f"**{item.get('safety_score','?')}**/10")
        row[3].markdown(
            f"<span class='ingredient-badge {badge}'>{emoji}</span> "
            f"{risk_badge_html(risk_l)}", unsafe_allow_html=True
        )
        funcs = item.get("function", [])
        row[4].markdown(", ".join(funcs[:2]) or "-")
        concerns = item.get("concerns", [])
        snippet = concerns[0][:45] + "…" if concerns and len(concerns[0]) > 45 else (concerns[0] if concerns else "-")
        row[5].markdown(f"<small style='color:#888;'>{snippet}</small>", unsafe_allow_html=True)


def render_skin_suitability(report: dict):
    suitability = report.get("skin_suitability", {})
    if not suitability:
        return
    st.markdown("### 💆 肤质适用性")
    cols = st.columns(len(suitability))
    for col, (skin_type, data) in zip(cols, suitability.items()):
        score_v = data.get("score", 5)
        label   = data.get("label", "一般")
        color   = "#28a745" if label == "适合" else ("#ffc107" if label == "一般" else "#dc3545")
        col.markdown(f"""
        <div style="text-align:center;padding:12px 6px;background:#f8f9fa;
                    border-radius:10px;border:1px solid #e9ecef;">
            <div style="font-size:12px;color:#666;">{skin_type}</div>
            <div style="font-size:1.5em;font-weight:700;color:{color};">{score_v}</div>
            <div style="font-size:12px;color:{color};font-weight:600;">{label}</div>
        </div>
        """, unsafe_allow_html=True)


def render_ai_report(report: dict):
    """AI / 本地规则引擎报告标签页"""
    st.markdown("### 🤖 AI 专业分析报告")

    # 生成快速摘要
    summary = generate_quick_summary(report)
    st.info(f"**快速摘要：** {summary}")

    col1, col2 = st.columns([3, 1])
    with col2:
        use_llm = bool(__import__("os").getenv("OPENAI_API_KEY"))
        model_label = "GPT-3.5-Turbo" if use_llm else "本地规则引擎"
        st.markdown(f"**报告引擎：** `{model_label}`")
        generate_btn = st.button("🚀 生成完整报告", type="primary", use_container_width=True)

    with col1:
        if "llm_report_cache" not in st.session_state:
            st.session_state["llm_report_cache"] = None
        if "llm_report_source" not in st.session_state:
            st.session_state["llm_report_source"] = None

    if generate_btn:
        with st.spinner("🤖 正在生成专业报告..."):
            report_text, source = generate_full_report(report, use_llm=use_llm)
            st.session_state["llm_report_cache"] = report_text
            st.session_state["llm_report_source"] = source

    if st.session_state.get("llm_report_cache"):
        source = st.session_state.get("llm_report_source", "local")
        badge = "🤖 GPT 生成" if source == "llm" else "⚙️ 本地规则引擎生成"
        st.caption(f"报告来源：{badge}")
        st.markdown(
            f'<div class="llm-report">{st.session_state["llm_report_cache"]}</div>',
            unsafe_allow_html=True
        )
        st.download_button(
            "📥 下载 MD 报告",
            data=st.session_state["llm_report_cache"],
            file_name=f"{report.get('brand','_')}_{report.get('product_name','_')}_report.md",
            mime="text/markdown",
            use_container_width=False,
        )
    else:
        st.caption("点击「生成完整报告」获取 AI 深度分析（含替代品推荐）")


def render_report(report: dict):
    brand   = report.get("brand", "")
    product = report.get("product_name", "")
    st.markdown(f"## 📋 分析报告：{brand} · {product}")
    st.caption(report.get("summary", ""))
    st.markdown("---")

    render_overview(report)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "⚗️ 组合风险", "⚠️ 风险成分", "🌸 过敏原",
        "🔬 成分全表", "💆 肤质适用", "🤖 AI 报告"
    ])

    with tab1:
        render_combination_risks(report)
        # 建议
        st.markdown("### 💊 使用建议")
        for rec in report.get("recommendations", []):
            st.markdown(f"> {rec}")

    with tab2:
        render_flagged_ingredients(report)
        highlights = report.get("safe_highlights", [])
        if highlights:
            st.markdown("### ✨ 优质成分亮点")
            badges_html = " ".join(
                f"<span class='ingredient-badge badge-safe'>✅ {h}</span>"
                for h in highlights
            )
            st.markdown(badges_html, unsafe_allow_html=True)

    with tab3:
        render_allergens(report)

    with tab4:
        render_all_ingredients(report)

    with tab5:
        render_skin_suitability(report)

    with tab6:
        render_ai_report(report)

    # 导出
    st.markdown("---")
    export_data = json.dumps(report, ensure_ascii=False, indent=2)
    st.download_button(
        "📥 导出完整 JSON 报告",
        data=export_data,
        file_name=f"{brand}_{product}_full_report.json",
        mime="application/json",
    )


# ─────────────────────────────────────────────
# 知识库搜索页
# ─────────────────────────────────────────────

def render_knowledge_base_page():
    st.markdown("## 📚 成分知识库搜索")
    st.caption("直接搜索成分安全数据，无需输入产品信息")

    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("🔍 搜索成分（INCI名或中文名）", placeholder="例如：Niacinamide / 烟酰胺")
    with col2:
        standard_filter = st.selectbox("查看禁用成分（法规）", ["不筛选", "FDA", "GB"])

    if keyword:
        results = search_ingredients(keyword, limit=20)
        if results:
            st.markdown(f"**找到 {len(results)} 个结果：**")
            for r in results:
                level = r.get("safety_level", "unknown")
                emoji = SAFETY_EMOJI.get(level, ("⚪",))[0]
                badge = get_badge_class(level)
                st.markdown(
                    f"<span class='ingredient-badge {badge}'>{emoji} {r['inci_name']}</span> "
                    f"**{r.get('cn_name','—')}** — 评分 {r.get('safety_score','?')}/10",
                    unsafe_allow_html=True
                )
        else:
            st.info("未找到匹配成分，请尝试其他关键词")

    if standard_filter != "不筛选":
        banned = get_banned_ingredients(standard=standard_filter)
        st.markdown(f"### 🚫 {standard_filter} 禁用/禁止成分（{len(banned)} 种）")
        if banned:
            for b in banned:
                st.markdown(
                    f"- `{b['inci_name']}` {'（' + b.get('cn_name','') + '）' if b.get('cn_name') else ''} "
                    f"— {b.get('warning','')}"
                )
        else:
            st.info("无记录")


# ─────────────────────────────────────────────
# 数据库状态页
# ─────────────────────────────────────────────

def render_db_status_page():
    st.markdown("## 📊 数据库状态")
    db_stats = get_db_stats()

    if not db_stats.get("initialized"):
        st.error("数据库未初始化")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🧪 成分总数",    db_stats["ingredients_count"])
    col2.metric("📋 产品记录",    db_stats["products_count"])
    col3.metric("📏 安全标准条目", db_stats["standards_count"])
    col4.metric("🕐 查询历史",    db_stats["history_count"])

    col5, col6, col7 = st.columns(3)
    col5.metric("🌸 过敏原数",   db_stats["allergens_count"])
    col6.metric("🚫 禁用记录数", db_stats["banned_records"])
    col7.metric("💾 DB大小(KB)", db_stats["db_size_kb"])

    st.markdown("---")
    st.markdown(f"**数据库路径：** `{db_stats['db_path']}`")

    st.markdown("### 🕐 最近查询历史")
    try:
        history = get_query_history_db(limit=10)
        if history:
            import pandas as pd
            df = pd.DataFrame(history)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("暂无查询历史")
    except Exception as e:
        st.error(f"历史记录加载失败：{e}")


# ─────────────────────────────────────────────
# 主逻辑
# ─────────────────────────────────────────────

def get_product_info(product_info: dict) -> dict:
    brand   = product_info.get("brand", "未知品牌")
    product = product_info.get("product", "未知产品")
    product_id_key = generate_product_id(brand, product)

    # 缓存检查（paste模式跳过）
    if product_info.get("input_method") != "paste":
        cached = check_cache(product_id_key)
        if cached:
            cached["_from_cache"] = True
            return cached

    # 获取成分
    if product_info.get("input_method") == "paste" and product_info.get("ingredients"):
        ingredients = product_info["ingredients"]
        source = "user_input"
    else:
        ingredients = web_scraper(brand, product)
        source = "web_scraper"

    # 分析
    report_obj  = analyze_product(brand, product, ingredients, save_to_db=True)
    report_dict = report_to_dict(report_obj)
    report_dict["_source"] = source
    report_dict["_from_cache"] = False

    # 缓存
    cache_result(product_id_key, report_dict)

    return report_dict


def main():
    page = render_sidebar()

    if "知识库" in page:
        render_knowledge_base_page()

    elif "数据库" in page:
        render_db_status_page()

    else:
        # 成分分析主页
        product_info = render_input_section()
        st.markdown("")

        if st.button("🚀 开始分析", type="primary",
                     disabled=(product_info is None), key="main_analyze_btn"):
            if product_info:
                with st.spinner("⏳ 正在分析成分..."):
                    try:
                        result = get_product_info(product_info)
                        if result.get("_from_cache"):
                            st.info("⚡ 结果来自缓存")
                        else:
                            st.success(f"✅ 分析完成！数据来源：{result.get('_source','N/A')}")
                        # 重置 AI 报告缓存
                        st.session_state["llm_report_cache"] = None
                        render_report(result)
                    except Exception as e:
                        st.error(f"❌ 分析出错：{str(e)}")
                        with st.expander("错误详情"):
                            import traceback
                            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
