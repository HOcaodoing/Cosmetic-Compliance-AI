"""
llm_report.py - AI 报告生成模块（Step 2）
Cosmetic Compliance AI

基于文档中的 Prompt 模板，使用 LLM 生成专业的化妆品成分分析报告。
支持：
  1. OpenAI GPT API（需配置 OPENAI_API_KEY）
  2. 本地规则引擎（API Key 未配置时的兜底方案，无需调用 LLM）

报告结构：
  - 报告摘要（总体安全评估）
  - 详细成分分析（分类：安全 / 需关注 / 高风险）
  - 使用建议（针对成分特性和风险）
  - 替代品推荐（针对高风险成分）
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Prompt 模板（来自文档，进一步完善）
# ─────────────────────────────────────────────

REPORT_PROMPT_TEMPLATE = """
你是一个专业的化妆品成分安全分析师，拥有深厚的化工专业背景。
请根据以下分析结果生成一份详细的成分安全报告。

**产品信息：**
- 品牌：{brand}
- 产品：{product}
- 成分总数：{total_ingredients} 种

**成分分析结果：**
- 安全成分（{safe_count}种）：{safe_list}
- 需关注成分（{caution_count}种）：{caution_list}
- 高风险/禁用成分（{risk_count}种）：{risk_list}
- 过敏原（{allergen_count}种）：{allergen_list}
- 成分组合风险：{combination_risks}

**合规状态：**
- FDA 合规：{fda_compliance}
- 中国法规合规：{gb_compliance}
- 综合安全评分：{overall_score}/10
- 整体风险等级：{overall_risk}

**报告要求：**
1. 使用专业的化工术语，充分体现专业知识
2. 报告结构清晰，包含摘要、详细分析、建议、替代品推荐四个部分
3. 对每个高风险成分提供详细的化学机理解释（包括化学名称、作用机制）
4. 针对组合风险进行深入的化学反应分析
5. 提供具体可行的使用建议，包括时间、频率、注意事项
6. 为高风险成分推荐3-5个更安全的替代成分
7. 语言专业但易于普通用户理解，避免晦涩术语
8. 若含有禁用成分，请明确说明相关法规条款

**输出格式（Markdown）：**

# {brand} {product} 成分安全分析报告

## 📋 报告摘要

## 🔬 详细成分分析

### 安全成分
### 需关注成分  
### 高风险/禁用成分
### 成分组合风险

## 💊 使用建议

## 🔄 替代品推荐

---
*本报告基于 FDA、中国化妆品安全技术规范及 EWG 数据库生成，仅供参考。*
"""


SIMPLE_REPORT_TEMPLATE = """
你是专业化妆品成分分析师。请用中文为以下产品生成简短的成分安全摘要（200字以内）：

产品：{brand} - {product}
安全评分：{overall_score}/10
风险等级：{overall_risk}
需关注成分：{risk_list}
组合风险：{combination_risks}

请直接输出分析结论，不需要标题。
"""

# ─────────────────────────────────────────────
# OpenAI API 调用
# ─────────────────────────────────────────────

def _call_openai(prompt: str,
                 model: str = "gpt-3.5-turbo",
                 max_tokens: int = 2000,
                 temperature: float = 0.3) -> Optional[str]:
    """
    调用 OpenAI API 生成报告

    Args:
        prompt:      完整的 Prompt 字符串
        model:       模型名称
        max_tokens:  最大输出 token 数
        temperature: 温度参数（越低越稳定）
    Returns:
        生成的报告文本，失败返回 None
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.info("[LLM] 未配置 OPENAI_API_KEY，跳过 LLM 调用")
        return None

    try:
        import openai  # 可选依赖
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是专业的化妆品成分安全分析师，具有化学和毒理学背景，"
                        "熟悉FDA、EU及中国化妆品法规。请用中文提供详细、准确的分析。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = response.choices[0].message.content
        logger.info(f"[LLM] 报告生成成功 (tokens: {response.usage.total_tokens})")
        return text
    except ImportError:
        logger.warning("[LLM] openai 包未安装，请运行: pip install openai")
        return None
    except Exception as e:
        logger.error(f"[LLM] API 调用失败: {e}")
        return None


# ─────────────────────────────────────────────
# 本地规则引擎（兜底 AI 报告）
# ─────────────────────────────────────────────

RISK_LEVEL_CN = {
    "Low": "低", "Medium": "中", "High": "高", "Critical": "严重"
}
COMPLIANCE_CN = {
    "compliant": "✅ 合规",
    "restricted": "⚠️ 含限制性成分",
    "prohibited": "🚫 含禁用成分",
}
SAFETY_LEVEL_CN = {
    "safe": "安全", "caution": "需关注",
    "moderate_concern": "中度关注", "concern": "高风险",
    "prohibited": "禁用", "unknown": "未知",
}

SAFER_ALTERNATIVES = {
    "Parabens": ["Phenoxyethanol（苯氧乙醇，≤1%）", "Sodium Benzoate（苯甲酸钠）", "Ethylhexylglycerin（乙基己基甘油）"],
    "Methylparaben": ["Phenoxyethanol", "Ethylhexylglycerin", "Benzyl Alcohol + Sorbic Acid组合"],
    "Propylparaben": ["Phenoxyethanol", "Sodium Levulinate", "Potassium Sorbate"],
    "Butylparaben": ["Phenoxyethanol", "Ethylhexylglycerin", "Caprylyl Glycol"],
    "Formaldehyde": ["Phenoxyethanol", "Benzyl Alcohol", "Gluconolactone（葡萄糖酸内酯）"],
    "Formaldehyde Releasers": ["Phenoxyethanol", "Sorbic Acid", "Ethylhexylglycerin"],
    "Triclosan": ["Tea Tree Oil（茶树油提取物）", "Salicylic Acid（低浓度）", "Ethylhexylglycerin"],
    "Fragrance": ["无香精配方（Fragrance-free）", "天然植物精油（需注意致敏原）"],
    "Parfum": ["无香精配方", "单一天然香气成分（如Rose Extract玫瑰提取物）"],
    "Alcohol Denat.": ["Glycerin（甘油）", "Butylene Glycol（丁二醇）", "Propylene Glycol（丙二醇）"],
    "Hydroquinone": ["Niacinamide（烟酰胺）", "Alpha-Arbutin（α-熊果苷）", "Tranexamic Acid（传明酸）", "Kojic Acid（曲酸）"],
    "Oxybenzone": ["Zinc Oxide（氧化锌，物理防晒）", "Titanium Dioxide（二氧化钛）", "Tinosorb S（生物素S）"],
    "Mercury Compounds": ["无替代品 — 立即停用并举报"],
    "Lead": ["无替代品 — 立即停用并举报"],
    "Arsenic": ["无替代品 — 立即停用并举报"],
    "Phthalates": ["Triethyl Citrate（柠檬酸三乙酯）", "Isosorbide Dimethyl Ether"],
    "DMDM Hydantoin": ["Phenoxyethanol", "Ethylhexylglycerin", "Leuconostoc Ferment Filtrate（乳酸菌发酵滤液）"],
    "Sodium Benzoate": ["Potassium Sorbate（山梨酸钾）", "Sodium Levulinate", "Ethylhexylglycerin"],
}


def _build_local_report(analysis_result: dict) -> str:
    """
    本地规则引擎生成结构化报告（无需 LLM）

    对应文档中的报告格式要求，输出 Markdown 格式。

    Args:
        analysis_result: report_to_dict() 的输出字典
    Returns:
        Markdown 格式报告字符串
    """
    brand   = analysis_result.get("brand", "未知品牌")
    product = analysis_result.get("product_name", "未知产品")
    score   = analysis_result.get("overall_safety_score", 5.0)
    level   = analysis_result.get("overall_safety_level", "unknown")
    risk    = analysis_result.get("overall_risk_level", "Medium")
    fda_c   = analysis_result.get("fda_compliance", "compliant")
    gb_c    = analysis_result.get("gb_compliance", "compliant")
    total   = analysis_result.get("total_ingredients", 0)

    all_ingredients = analysis_result.get("ingredient_analyses", [])
    flagged = analysis_result.get("flagged_ingredients", [])
    allergens = analysis_result.get("allergens_found", [])
    combo_risks = analysis_result.get("combination_risks", [])
    highlights = analysis_result.get("safe_highlights", [])

    # 分类
    safe_ings    = [a for a in all_ingredients if not a.get("is_flagged") and a.get("risk_level", "Low") == "Low"]
    caution_ings = [a for a in flagged if a.get("risk_level", "Low") in ("Medium",)]
    high_risk    = [a for a in flagged if a.get("risk_level", "Low") in ("High", "Critical")]

    # ── 摘要 ──────────────────────────────────
    score_bar = "🟢" * int(score / 2) + "⚪" * (5 - int(score / 2))
    summary_text = f"""
# {brand} · {product} 成分安全分析报告

## 📋 报告摘要

| 指标 | 结果 |
|------|------|
| 成分总数 | {total} 种 |
| 综合安全评分 | **{score}/10** {score_bar} |
| 安全等级 | **{SAFETY_LEVEL_CN.get(level, level)}** |
| 整体风险等级 | **{RISK_LEVEL_CN.get(risk, risk)}** |
| FDA 合规性 | {COMPLIANCE_CN.get(fda_c, fda_c)} |
| 中国法规合规性 | {COMPLIANCE_CN.get(gb_c, gb_c)} |
| 需关注成分 | {len(flagged)} 种 |
| 已知过敏原 | {len(allergens)} 种 |
| 成分组合风险 | {len(combo_risks)} 项 |

"""

    # ── 详细成分分析 ──────────────────────────
    detail_text = "## 🔬 详细成分分析\n\n"

    # 安全成分
    detail_text += f"### ✅ 安全成分（{len(safe_ings)} 种）\n\n"
    if highlights:
        detail_text += f"**⭐ 优质功效成分：** {', '.join(highlights)}\n\n"
    if safe_ings:
        for ing in safe_ings[:10]:  # 最多显示10种
            cn = f"（{ing['cn_name']}）" if ing.get("cn_name") else ""
            funcs = "、".join(ing.get("function", [])[:2])
            detail_text += f"- **{ing['inci_name']}** {cn} — {funcs or '成膜/基质'}\n"
        if len(safe_ings) > 10:
            detail_text += f"  *...及其他 {len(safe_ings) - 10} 种安全成分*\n"
    else:
        detail_text += "*暂无完全安全评级的成分*\n"
    detail_text += "\n"

    # 需关注成分
    detail_text += f"### ⚠️ 需关注成分（{len(caution_ings)} 种）\n\n"
    if caution_ings:
        for ing in caution_ings:
            cn = f"（{ing['cn_name']}）" if ing.get("cn_name") else ""
            score_i = ing.get("safety_score", 5)
            detail_text += f"- **{ing['inci_name']}** {cn} — 安全评分 {score_i}/10\n"
            for concern in ing.get("concerns", [])[:2]:
                detail_text += f"  - ⚠️ {concern}\n"
            if ing.get("max_concentration") and ing["max_concentration"] != "Not specified":
                detail_text += f"  - 📏 法规限量：{ing['max_concentration']}\n"
    else:
        detail_text += "*未检测到中度风险成分*\n"
    detail_text += "\n"

    # 高风险/禁用
    detail_text += f"### 🚨 高风险 / 禁用成分（{len(high_risk)} 种）\n\n"
    if high_risk:
        for ing in high_risk:
            cn = f"（{ing['cn_name']}）" if ing.get("cn_name") else ""
            fda_s = ing.get("fda_status", "")
            gb_s  = ing.get("gb_status", "")
            detail_text += f"#### ⛔ {ing['inci_name']} {cn}\n"
            detail_text += f"- **安全评分：** {ing.get('safety_score', '?')}/10\n"
            detail_text += f"- **FDA状态：** `{fda_s}`\n"
            detail_text += f"- **中国法规：** `{gb_s}`\n"
            if ing.get("description"):
                detail_text += f"- **说明：** {ing['description']}\n"
            for concern in ing.get("concerns", []):
                detail_text += f"- ⚠️ {concern}\n"
            # 替代品
            alts = SAFER_ALTERNATIVES.get(ing["inci_name"], [])
            if alts:
                detail_text += f"- **🔄 更安全替代品：** {' / '.join(alts[:3])}\n"
            detail_text += "\n"
    else:
        detail_text += "*✅ 未检测到禁用或极高风险成分*\n\n"

    # 组合风险
    detail_text += f"### ⚗️ 成分组合风险（{len(combo_risks)} 项）\n\n"
    if combo_risks:
        severity_icon = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "Critical": "⛔"}
        for cr in combo_risks:
            icon = severity_icon.get(cr.get("severity", "Medium"), "🟠")
            detail_text += f"{icon} **{cr['ingredient_a']}** + **{cr['ingredient_b']}**\n\n"
            detail_text += f"> {cr['risk_description']}\n\n"
            detail_text += f"> 风险等级：**{RISK_LEVEL_CN.get(cr.get('severity', 'Medium'), cr.get('severity', ''))}**\n\n"
    else:
        detail_text += "*✅ 未检测到成分组合风险*\n\n"

    # ── 使用建议 ──────────────────────────────
    recs = analysis_result.get("recommendations", [])
    usage_text = "## 💊 使用建议\n\n"
    if recs:
        for rec in recs:
            usage_text += f"{rec}\n\n"
    else:
        usage_text += "该产品成分整体安全，按照产品说明书正常使用即可。\n\n"

    # ── 过敏原清单 ────────────────────────────
    allergen_text = ""
    if allergens:
        allergen_text = "## 🌸 过敏原清单\n\n"
        allergen_text += f"该产品含有 **{len(allergens)}** 种已知致敏原，过敏体质人群请注意：\n\n"
        for a in allergens:
            allergen_text += f"- `{a}`\n"
        allergen_text += "\n> 建议：首次使用前进行48小时贴肤测试（耳后或内腕）。\n\n"

    # ── 替代品推荐 ────────────────────────────
    alt_text = "## 🔄 替代品推荐\n\n"
    all_alts = {}
    for ing in flagged:
        name = ing.get("inci_name", "")
        alts = SAFER_ALTERNATIVES.get(name, [])
        if alts:
            all_alts[name] = alts

    if all_alts:
        for ing_name, alts in all_alts.items():
            cn = next((a.get("cn_name", "") for a in flagged if a.get("inci_name") == ing_name), "")
            cn_str = f"（{cn}）" if cn else ""
            alt_text += f"**{ing_name}{cn_str}** 可替换为：\n"
            for a in alts:
                alt_text += f"  - {a}\n"
            alt_text += "\n"
    else:
        alt_text += "*当前成分未发现需要替代的高风险成分。*\n\n"

    # ── 结语 ─────────────────────────────────
    footer = """---
*本报告由 Cosmetic Compliance AI 自动生成，数据来源：FDA 21 CFR / 中国化妆品安全技术规范(2015) / EWG Skin Deep。*  
*本报告仅供参考，不构成医疗建议。具体用药请遵医嘱。*
"""

    return summary_text + detail_text + usage_text + allergen_text + alt_text + footer


# ─────────────────────────────────────────────
# 公共入口
# ─────────────────────────────────────────────

def generate_full_report(analysis_result: dict,
                          use_llm: bool = True) -> tuple[str, str]:
    """
    生成完整的 AI 分析报告

    优先使用 LLM（OpenAI），若不可用则使用本地规则引擎。

    Args:
        analysis_result: report_to_dict() 的输出字典
        use_llm:         是否尝试调用 LLM
    Returns:
        (report_text, source)  — source: 'llm' 或 'local'
    """
    brand   = analysis_result.get("brand", "未知品牌")
    product = analysis_result.get("product_name", "未知产品")
    score   = analysis_result.get("overall_safety_score", 5.0)
    risk    = analysis_result.get("overall_risk_level", "Medium")
    fda_c   = analysis_result.get("fda_compliance", "compliant")
    gb_c    = analysis_result.get("gb_compliance", "compliant")
    total   = analysis_result.get("total_ingredients", 0)

    flagged      = analysis_result.get("flagged_ingredients", [])
    all_ings     = analysis_result.get("ingredient_analyses", [])
    allergens    = analysis_result.get("allergens_found", [])
    combo_risks  = analysis_result.get("combination_risks", [])

    safe_list    = [a["inci_name"] for a in all_ings if not a.get("is_flagged")]
    caution_list = [a["inci_name"] for a in flagged if a.get("risk_level") in ("Low", "Medium")]
    risk_list    = [
        f"{a['inci_name']}（{a.get('cn_name', '')}，{a.get('fda_status', '')}）"
        for a in flagged if a.get("risk_level") in ("High", "Critical")
    ]
    combo_text = "; ".join(
        f"{c['ingredient_a']}+{c['ingredient_b']}: {c['risk_description'][:40]}..."
        for c in combo_risks
    ) or "无"

    # 尝试 LLM
    if use_llm and os.getenv("OPENAI_API_KEY"):
        prompt = REPORT_PROMPT_TEMPLATE.format(
            brand=brand, product=product,
            total_ingredients=total,
            safe_count=len(safe_list),
            safe_list=", ".join(safe_list[:8]),
            caution_count=len(caution_list),
            caution_list=", ".join(caution_list[:5]),
            risk_count=len(risk_list),
            risk_list=", ".join(risk_list[:5]),
            allergen_count=len(allergens),
            allergen_list=", ".join(allergens[:5]) or "无",
            combination_risks=combo_text,
            fda_compliance=COMPLIANCE_CN.get(fda_c, fda_c),
            gb_compliance=COMPLIANCE_CN.get(gb_c, gb_c),
            overall_score=score,
            overall_risk=risk,
        )
        llm_text = _call_openai(prompt, max_tokens=2500)
        if llm_text:
            return llm_text, "llm"

    # 兜底：本地规则引擎
    local_text = _build_local_report(analysis_result)
    return local_text, "local"


def generate_quick_summary(analysis_result: dict) -> str:
    """
    生成简短摘要（用于 Streamlit 侧边栏或通知提示）

    Args:
        analysis_result: report_to_dict() 的输出字典
    Returns:
        一段200字以内的中文摘要
    """
    score  = analysis_result.get("overall_safety_score", 5.0)
    risk   = analysis_result.get("overall_risk_level", "Medium")
    fda    = analysis_result.get("fda_compliance", "compliant")
    gb     = analysis_result.get("gb_compliance", "compliant")
    flagged_count = len(analysis_result.get("flagged_ingredients", []))
    combo_count   = len(analysis_result.get("combination_risks", []))

    level_text = {
        "Low": "整体安全，适合日常使用",
        "Medium": "存在少量需关注成分，建议敏感肌谨慎",
        "High": "含多种高风险成分，请谨慎使用",
        "Critical": "含禁用成分，强烈建议停止使用",
    }.get(risk, "")

    lines = [
        f"综合安全评分 **{score}/10**，{level_text}。",
        f"共 {flagged_count} 种成分需要关注。",
    ]
    if combo_count:
        lines.append(f"检测到 {combo_count} 种成分组合风险。")
    if fda != "compliant":
        lines.append(f"⚠️ FDA 合规状态：{COMPLIANCE_CN.get(fda, fda)}。")
    if gb != "compliant":
        lines.append(f"⚠️ 中国法规合规状态：{COMPLIANCE_CN.get(gb, gb)}。")

    return " ".join(lines)
