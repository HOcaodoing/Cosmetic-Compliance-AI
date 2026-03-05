"""
report_generator.py - AI 分析报告生成模块
Cosmetic Compliance AI - 第三步

调用 Claude LLM 将成分分析数据转化为专业、易懂的自然语言合规性报告。
支持 Anthropic Claude API，无 API Key 时优雅降级并给出配置提示。

报告输出结构（generate_compliance_report 返回）：
{
    "product_info":     {"brand": ..., "product_name": ...},
    "summary":          "总体安全性评价（纯文本）",
    "detailed_analysis": {
        "safe_ingredients":   [{"name": ..., "function": ..., "safety_level": ...}],
        "risk_ingredients":   [{"name": ..., "risk_level": ..., "reason": ..., "recommendation": ...}],
        "interaction_warnings": ["成分相互作用警告"],
    },
    "report_content":   "Markdown 格式完整报告正文（LLM 生成）",
    "final_recommendation": "最终使用建议",
    "generated_at":     ISO 时间字符串,
    "version":          "1.0",
    "success":          True/False,
    "model":            使用的模型名称（成功时）,
    "tokens_used":      {"input": N, "output": N}（成功时）,
    "error":            错误信息（失败时）,
}
"""

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Prompt 设计
# ─────────────────────────────────────────────

def generate_report_prompt(analysis_result: dict) -> str:
    """
    根据分析结果构建专业报告生成 Prompt

    Args:
        analysis_result: 来自 analyzer.report_to_dict() 的字典
    Returns:
        格式化的 Prompt 字符串
    """
    brand         = analysis_result.get("brand", "未知品牌")
    product_name  = analysis_result.get("product_name", "未知产品")
    overall_score = analysis_result.get("overall_safety_score", 5.0)
    overall_level = analysis_result.get("overall_safety_level", "unknown")
    fda_status    = analysis_result.get("fda_compliance", "unknown")
    gb_status     = analysis_result.get("gb_compliance", "unknown")
    highlights    = analysis_result.get("safe_highlights", [])

    level_map = {
        "safe":             "安全",
        "caution":          "需关注",
        "moderate_concern": "中度关注",
        "concern":          "高风险",
    }

    # 安全成分（前10个，排除风险成分）
    safe_ings = [
        ing for ing in analysis_result.get("ingredient_analyses", [])
        if not ing.get("is_flagged", False)
    ]
    safe_names = [
        f"{i['inci_name']}{'（' + i['cn_name'] + '）' if i.get('cn_name') else ''}"
        for i in safe_ings[:10]
    ]

    # 风险成分详情
    risk_ings = analysis_result.get("flagged_ingredients", [])
    risk_lines = []
    for ing in risk_ings:
        name     = ing["inci_name"]
        cn       = f"（{ing['cn_name']}）" if ing.get("cn_name") else ""
        score    = ing.get("safety_score", "?")
        concerns = ing.get("concerns", [])
        fda_s    = ing.get("fda_status", "not_listed")
        gb_s     = ing.get("gb_status", "not_listed")
        line     = f"- **{name}{cn}**：安全评分 {score}/10，FDA={fda_s}，GB={gb_s}"
        if concerns:
            line += f"\n  注意：{'; '.join(concerns[:3])}"
        risk_lines.append(line)

    # 肤质信息
    skin_lines = [
        f"{skin}：{data.get('score', '?')}分（{data.get('label', '?')}）"
        for skin, data in analysis_result.get("skin_suitability", {}).items()
    ]

    prompt = f"""你是一位资深化妆品配方师兼合规专家，拥有10年以上化工背景和皮肤科学经验。\
请根据以下成分分析数据，为消费者撰写一份专业、易懂的合规性分析报告。

---
## 📦 产品信息
- 品牌：{brand}
- 产品：{product_name}
- 综合安全评分：{overall_score}/10（{level_map.get(overall_level, overall_level)}）
- FDA 合规状态：{fda_status}
- 中国 GB 合规状态：{gb_status}

## ✅ 主要安全成分
{', '.join(safe_names) if safe_names else '暂无数据'}

## ⭐ 功效亮点成分
{', '.join(highlights) if highlights else '暂无'}

## ⚠️ 需关注成分
{chr(10).join(risk_lines) if risk_lines else '✅ 未发现风险成分'}

## 💆 肤质适用性评分
{', '.join(skin_lines)}

---
## 报告格式要求

请严格按以下 Markdown 结构输出，总字数控制在 450 字以内：

### 🏷️ 总体评价
（1-2句话，概括产品整体安全性和配方风格）

### ⭐ 成分亮点解析
（重点介绍2-3个优质功效成分，说明其化学原理和护肤机制，体现专业性）

### ⚠️ 风险成分详解
（针对每个风险成分，从化工安全角度说明潜在危害机制和具体使用建议；\
若无风险成分，写"本产品未发现需特别警示的成分"）

### 💆 肤质使用指南
（基于成分组合特点，针对2-3种肤质给出差异化使用建议）

### 📋 合规性小结
（简述 FDA 和中国法规合规情况；若有限制成分，指出关注点）

写作要求：
- 语言专业但通俗，避免过度堆砌术语
- 对风险成分客观评估，不夸大也不淡化
- 整体基调积极、帮助性强
- 适当引用化学机制或皮肤科学原理以增加可信度
"""
    return prompt


# ─────────────────────────────────────────────
# AI 报告生成（主函数）
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 成分相互作用检测（规则引擎）
# ─────────────────────────────────────────────

# 已知的成分相互作用风险规则
_INTERACTION_RULES: list[tuple[str, str, str]] = [
    (
        "Sodium Benzoate", "Ascorbic Acid",
        "苯甲酸钠 + 抗坏血酸（维C）：在热和光照条件下可能生成微量苯，建议避免同时使用。"
    ),
    (
        "Sodium Benzoate", "Vitamin C",
        "苯甲酸钠 + 维生素C：高温或光照下存在苯的生成风险，建议低温避光保存。"
    ),
    (
        "Retinol", "Salicylic Acid",
        "视黄醇 + 水杨酸：同时使用可能加重皮肤刺激，建议分时段使用（早/晚分开）。"
    ),
    (
        "Retinol", "Glycolic Acid",
        "视黄醇 + 乙醇酸（果酸）：双重酸化可能导致皮肤屏障受损，敏感肌请勿同时使用。"
    ),
    (
        "Niacinamide", "Ascorbic Acid",
        "烟酰胺 + 抗坏血酸：高浓度同时使用可能发生反应生成黄色产物烟黄素，建议错开使用时间。"
    ),
    (
        "Niacinamide", "Vitamin C",
        "烟酰胺 + 维生素C：浓度较高时可能降低彼此功效，建议早晚分开使用。"
    ),
    (
        "Hydrogen Peroxide", "Copper Peptide",
        "过氧化氢 + 铜肽：氧化剂会破坏铜肽活性，严禁同时使用。"
    ),
    (
        "AHA", "BHA",
        "果酸（AHA）+ 水杨酸（BHA）：叠加使用可能过度去角质，皮肤屏障受损风险增加。"
    ),
]


def detect_interaction_warnings(ingredient_names: list[str]) -> list[str]:
    """
    检测成分列表中存在的已知相互作用风险

    Args:
        ingredient_names: 成分 INCI 名称列表（大小写不敏感）
    Returns:
        警告文字列表，无风险则返回空列表
    """
    names_lower = {n.lower() for n in ingredient_names}
    warnings: list[str] = []
    for a, b, msg in _INTERACTION_RULES:
        if a.lower() in names_lower and b.lower() in names_lower:
            warnings.append(msg)
    return warnings


# ─────────────────────────────────────────────
# 结构化 detailed_analysis 构建
# ─────────────────────────────────────────────

def build_detailed_analysis(analysis_result: dict) -> dict:
    """
    从 analyzer.report_to_dict() 的结果中提取结构化的 detailed_analysis

    Returns:
        {
            "safe_ingredients":   [{"name", "function", "safety_level"}],
            "risk_ingredients":   [{"name", "risk_level", "reason", "recommendation"}],
            "interaction_warnings": [str],
        }
    """
    # ── 安全成分列表 ──
    safe_ingredients = [
        {
            "name":         ing["inci_name"],
            "function":     ", ".join(ing.get("function", [])) or "保湿/基础成分",
            "safety_level": ing.get("safety_level", "unknown"),
        }
        for ing in analysis_result.get("ingredient_analyses", [])
        if not ing.get("is_flagged", False)
    ]

    # ── 风险成分列表（使用规则引擎） ──
    risk_ingredients = []
    for ing in analysis_result.get("flagged_ingredients", []):
        assessment = generate_risk_assessment(
            ingredient_name=ing["inci_name"],
            safety_score=ing.get("safety_score", 5),
            concerns=ing.get("concerns", []),
            fda_status=ing.get("fda_status", "not_listed"),
            gb_status=ing.get("gb_status", "not_listed"),
        )
        risk_ingredients.append({
            "name":           ing["inci_name"],
            "risk_level":     assessment["risk_level"],
            "reason":         assessment["reason"],
            "recommendation": assessment["recommendation"],
        })

    # ── 成分相互作用警告 ──
    all_names = [
        ing["inci_name"]
        for ing in analysis_result.get("ingredient_analyses", [])
    ]
    interaction_warnings = detect_interaction_warnings(all_names)

    return {
        "safe_ingredients":     safe_ingredients,
        "risk_ingredients":     risk_ingredients,
        "interaction_warnings": interaction_warnings,
    }


def generate_compliance_report(
    analysis_result: dict,
    api_key: Optional[str] = None,
) -> dict:
    """
    调用 Claude LLM 生成自然语言合规性报告

    Args:
        analysis_result: report_to_dict() 返回的分析结果字典
        api_key:         Anthropic API Key（为空则读取环境变量 ANTHROPIC_API_KEY）
    Returns:
        完整报告字典（见模块文档字符串中的结构说明）
    """
    brand        = analysis_result.get("brand", "未知品牌")
    product_name = analysis_result.get("product_name", "未知产品")
    base_info    = {"brand": brand, "product_name": product_name}

    # ── 预先构建 detailed_analysis（不依赖 LLM）──
    detailed = build_detailed_analysis(analysis_result)

    # ── 最终建议（取 recommendations 第一条作为 final_recommendation）──
    recs = analysis_result.get("recommendations", [])
    final_rec = recs[0] if recs else "请结合个人肤质情况合理使用，如有疑问请咨询皮肤科医生。"

    # ── 获取 API Key ──
    key = (api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()

    if not key:
        logger.warning("[ReportGenerator] ANTHROPIC_API_KEY 未设置，跳过 AI 报告生成")
        return {
            "product_info":      base_info,
            "summary":           analysis_result.get("summary", ""),
            "detailed_analysis": detailed,
            "report_content": (
                "> ⚙️ **AI 深度分析未启用**\n\n"
                "请在项目根目录创建 `.env` 文件并添加：\n\n"
                "```\nANTHROPIC_API_KEY=your_api_key_here\n```\n\n"
                "配置完成后重启 Streamlit 应用，即可启用 Claude AI 深度分析功能。\n\n"
                "获取 API Key：[Anthropic Console](https://console.anthropic.com)"
            ),
            "final_recommendation": final_rec,
            "generated_at": datetime.now().isoformat(),
            "version":      "1.0",
            "success":      False,
            "error":        "ANTHROPIC_API_KEY not set",
        }

    # ── 调用 Claude API ──
    try:
        import anthropic  # noqa: PLC0415

        client = anthropic.Anthropic(api_key=key)
        prompt = generate_report_prompt(analysis_result)

        logger.info(f"[ReportGenerator] 调用 Claude API：{brand} · {product_name}")

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        report_content = message.content[0].text

        logger.info(
            f"[ReportGenerator] 报告生成成功，"
            f"tokens: in={message.usage.input_tokens} out={message.usage.output_tokens}"
        )

        return {
            "product_info":      base_info,
            "summary":           analysis_result.get("summary", ""),
            "detailed_analysis": detailed,
            "report_content":    report_content,
            "final_recommendation": final_rec,
            "generated_at":      datetime.now().isoformat(),
            "version":           "1.0",
            "success":           True,
            "model":             "claude-sonnet-4-6",
            "tokens_used": {
                "input":  message.usage.input_tokens,
                "output": message.usage.output_tokens,
            },
        }

    except ImportError:
        msg = "anthropic 包未安装。请运行：`pip install anthropic`，然后重启应用。"
        logger.error(f"[ReportGenerator] {msg}")
        return {
            "product_info":      base_info,
            "summary":           analysis_result.get("summary", ""),
            "detailed_analysis": detailed,
            "report_content":    f"> ❌ **依赖缺失**\n\n{msg}",
            "final_recommendation": final_rec,
            "generated_at":      datetime.now().isoformat(),
            "version":           "1.0",
            "success":           False,
            "error":             msg,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error(f"[ReportGenerator] AI 报告生成异常: {exc}")
        return {
            "product_info":      base_info,
            "summary":           analysis_result.get("summary", ""),
            "detailed_analysis": detailed,
            "report_content":    f"> ❌ **AI 报告生成失败**\n\n错误信息：`{exc}`",
            "final_recommendation": final_rec,
            "generated_at":      datetime.now().isoformat(),
            "version":           "1.0",
            "success":           False,
            "error":             str(exc),
        }


# ─────────────────────────────────────────────
# 规则引擎：单成分风险评估（无需 API Key）
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 浓度限值参考表（参考 GB 2760 / FDA 21 CFR）
# ─────────────────────────────────────────────
_CONCENTRATION_LIMITS: dict[str, dict] = {
    "phenoxyethanol":   {"max_pct": 1.0,  "standard": "EU Cosmetics Regulation Annex V"},
    "methylparaben":    {"max_pct": 0.4,  "standard": "GB 规范附录B"},
    "propylparaben":    {"max_pct": 0.14, "standard": "EU / GB 2760"},
    "butylparaben":     {"max_pct": 0.14, "standard": "EU / GB 2760"},
    "salicylic acid":   {"max_pct": 2.0,  "standard": "FDA OTC / GB 规范附录B"},
    "resorcinol":       {"max_pct": 0.5,  "standard": "EU Cosmetics Regulation Annex III"},
    "hydrogen peroxide":{"max_pct": 4.0,  "standard": "FDA 21 CFR 700"},
    "hydroquinone":     {"max_pct": 2.0,  "standard": "FDA OTC（处方级）"},
    "alcohol denat.":   {"max_pct": 70.0, "standard": "参考最终产品类别"},
    "formaldehyde":     {"max_pct": 0.2,  "standard": "EU Cosmetics Regulation Annex V / GB 规范"},
}


def generate_risk_assessment(
    ingredient_name: str,
    safety_score: int = 5,
    concerns: list | None = None,
    fda_status: str = "not_listed",
    gb_status: str  = "not_listed",
    concentration: float | None = None,
) -> dict:
    """
    基于化工规则引擎对单个成分生成风险评估（不依赖 LLM）

    Args:
        ingredient_name: INCI 成分名称
        safety_score:    安全评分 (1-10)，默认 5
        concerns:        已知注意事项列表，默认 None
        fda_status:      FDA 合规状态字符串
        gb_status:       GB 合规状态字符串
        concentration:   实际使用浓度（百分比，0-100），可选。
                         当提供时，将与法规限值对比并调整风险等级。
    Returns:
        {ingredient, risk_level, risk_label, reason, recommendation, concerns,
         concentration_info}（concentration_info 仅在 concentration 参数非空时出现）
    """
    if concerns is None:
        concerns = []
    RISK_LABELS = {"low": "低风险", "medium": "中风险", "high": "高风险"}

    # ── 浓度超限检测（优先级最高）──
    concentration_info: dict | None = None
    if concentration is not None:
        name_key = ingredient_name.lower()
        limit_data = _CONCENTRATION_LIMITS.get(name_key)
        if limit_data:
            max_pct = limit_data["max_pct"]
            standard = limit_data["standard"]
            if concentration > max_pct:
                concentration_info = {
                    "actual_pct":  concentration,
                    "max_pct":     max_pct,
                    "standard":    standard,
                    "over_limit":  True,
                }
                risk_level     = "high"
                reason         = (
                    f"实际浓度 {concentration}% 超过法规限值 {max_pct}%"
                    f"（参考标准：{standard}）。"
                )
                recommendation = (
                    "请确认产品配方浓度符合法规要求，超限产品存在安全隐患，建议停止使用。"
                )
                return {
                    "ingredient":        ingredient_name,
                    "risk_level":        risk_level,
                    "risk_label":        RISK_LABELS[risk_level],
                    "reason":            reason,
                    "recommendation":    recommendation,
                    "concerns":          concerns,
                    "concentration_info": concentration_info,
                }
            else:
                concentration_info = {
                    "actual_pct":  concentration,
                    "max_pct":     max_pct,
                    "standard":    standard,
                    "over_limit":  False,
                }

    # ── 法规状态优先 ──
    if fda_status == "prohibited" or gb_status == "prohibited":
        risk_level     = "high"
        reason         = f"该成分已被监管机构明确禁用（FDA: {fda_status}，GB: {gb_status}）。"
        recommendation = "强烈建议避免使用，或联系品牌方确认成分合规性。"

    elif fda_status == "restricted" or gb_status == "restricted":
        risk_level     = "medium"
        reason         = (
            concerns[0] if concerns
            else f"该成分属受限成分（FDA: {fda_status}，GB: {gb_status}），需控制使用浓度。"
        )
        recommendation = "请确认产品成分浓度符合法规上限，敏感肌及孕妇请谨慎使用。"

    elif safety_score >= 8:
        risk_level     = "low"
        reason         = "该成分在推荐浓度下安全性良好，符合国际化妆品安全标准。"
        recommendation = "正常使用安全，无需特殊注意。"

    elif safety_score >= 5:
        risk_level     = "medium"
        reason         = concerns[0] if concerns else "该成分存在一定使用限制，请关注浓度及适用人群。"
        recommendation = "敏感肌建议进行48小时贴肤测试；孕妇及婴幼儿请谨慎使用。"

    else:
        risk_level     = "high"
        reason         = concerns[0] if concerns else "该成分风险评分较低，多国法规对其有严格限制。"
        recommendation = "建议避免使用，或在皮肤科医生指导下谨慎选用。"

    result = {
        "ingredient":     ingredient_name,
        "risk_level":     risk_level,
        "risk_label":     RISK_LABELS[risk_level],
        "reason":         reason,
        "recommendation": recommendation,
        "concerns":       concerns,
    }
    if concentration_info is not None:
        result["concentration_info"] = concentration_info
    return result
