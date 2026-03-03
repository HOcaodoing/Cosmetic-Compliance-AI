"""
analyzer.py - 成分分析引擎（Step 2 深度升级版）
Cosmetic Compliance AI

新增：
  - 组合风险（苯甲酸钠×维C → 苯生成等）的交叉检测
  - 过敏原识别与汇总
  - 基于 SQLite 知识库的精准查询
  - 风险等级 5 级分类（safe/caution/moderate_concern/concern/prohibited）
  - 数据库持久化：产品 + 成分关联保存
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from database import (
    init_database, get_ingredient_details, upsert_product,
    save_product_ingredients, DB_PATH
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INGREDIENTS_DB_PATH = DATA_DIR / "ingredients_db.json"
FDA_RESTRICTED_PATH = DATA_DIR / "fda_restricted.json"
GB_RESTRICTED_PATH  = DATA_DIR / "gb_restricted.json"


# ─────────────────────────────────────────────
# 数据类（Step 2 扩充）
# ─────────────────────────────────────────────

@dataclass
class IngredientAnalysis:
    """单个成分的完整分析结果"""
    inci_name: str
    cn_name: str = ""
    function: list[str] = field(default_factory=list)
    safety_score: int = 5
    safety_level: str = "unknown"
    ewg_score: int = 0
    description: str = ""
    concerns: list[str] = field(default_factory=list)
    fda_status: str = "not_listed"
    gb_status: str = "not_listed"
    max_concentration: str = "Not specified"
    suitable_skin: list[str] = field(default_factory=list)
    allergen: bool = False
    combination_warnings: list[dict] = field(default_factory=list)
    is_flagged: bool = False
    risk_level: str = "Low"      # Low / Medium / High / Critical


@dataclass
class CombinationRisk:
    """成分组合风险"""
    ingredient_a: str
    ingredient_b: str
    risk_description: str
    severity: str  # Low / Medium / High / Critical


@dataclass
class ComplianceReport:
    """完整合规性分析报告（Step 2 扩充版）"""
    brand: str
    product_name: str
    total_ingredients: int
    overall_safety_score: float = 5.0
    overall_safety_level: str = "unknown"
    overall_risk_level: str = "Low"
    fda_compliance: str = "compliant"
    gb_compliance: str = "compliant"
    ingredient_analyses: list[IngredientAnalysis] = field(default_factory=list)
    flagged_ingredients: list[IngredientAnalysis] = field(default_factory=list)
    allergens_found: list[str] = field(default_factory=list)
    combination_risks: list[CombinationRisk] = field(default_factory=list)
    safe_highlights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    skin_suitability: dict = field(default_factory=dict)
    summary: str = ""
    product_id: int | None = None


# ─────────────────────────────────────────────
# JSON 知识库（兜底，当DB未初始化时使用）
# ─────────────────────────────────────────────

class _JsonKB:
    """JSON 文件知识库（兜底方案）"""
    _instance: Optional["_JsonKB"] = None

    def __init__(self):
        def _load(p):
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    return {}
            return {}

        raw = _load(INGREDIENTS_DB_PATH)
        self.ingredients: dict[str, dict] = {
            item["inci_name"].lower(): item
            for item in raw.get("ingredients", [])
        }
        raw_fda = _load(FDA_RESTRICTED_PATH)
        self.fda_restricted: list[dict] = raw_fda.get("restricted_ingredients", [])
        raw_gb = _load(GB_RESTRICTED_PATH)
        self.gb_restricted: list[dict] = raw_gb.get("restricted_ingredients", [])

    @classmethod
    def get(cls) -> "_JsonKB":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


# Public alias so tests can do: from analyzer import KnowledgeBase
KnowledgeBase = _JsonKB


# ─────────────────────────────────────────────
# 组合风险知识库
# ─────────────────────────────────────────────

COMBINATION_RISKS: list[dict] = [
    {
        "a_names": ["sodium benzoate"],
        "b_names": ["ascorbic acid", "vitamin c"],
        "risk": "苯甲酸钠与维C在热/光照环境下可生成苯（苯是已知致癌物，IARC I类）",
        "severity": "High",
    },
    {
        "a_names": ["retinol", "vitamin a"],
        "b_names": ["ascorbic acid", "vitamin c"],
        "risk": "维A醇与维C（低pH）可能相互降解，降低各自稳定性和功效",
        "severity": "Medium",
    },
    {
        "a_names": ["niacinamide"],
        "b_names": ["ascorbic acid", "vitamin c"],
        "risk": "高浓度烟酰胺与维C可能结合生成黄色烟酸，降低美白功效（低pH环境）",
        "severity": "Low",
    },
    {
        "a_names": ["aha", "glycolic acid", "lactic acid", "ascorbic acid"],
        "b_names": ["retinol", "vitamin a"],
        "risk": "酸类（低pH）与视黄醇同用可增加刺激风险，破坏皮肤屏障",
        "severity": "Medium",
    },
    {
        "a_names": ["salicylic acid"],
        "b_names": ["retinol"],
        "risk": "水杨酸与视黄醇同用大幅增加刺激和脱皮风险",
        "severity": "Medium",
    },
    {
        "a_names": ["alcohol denat.", "ethanol"],
        "b_names": ["retinol"],
        "risk": "高浓度酒精会溶解视黄醇并加速其降解，同时加剧皮肤刺激",
        "severity": "Medium",
    },
    {
        "a_names": ["hydrogen peroxide"],
        "b_names": ["retinol", "vitamin c", "ascorbic acid"],
        "risk": "过氧化氢会氧化视黄醇/维C，使其失活",
        "severity": "High",
    },
    {
        "a_names": ["benzoyl peroxide"],
        "b_names": ["retinol"],
        "risk": "过氧化苯甲酰会氧化视黄醇，降低功效并增加刺激",
        "severity": "Medium",
    },
]


def _check_combination_risks(ingredients: list[str]) -> list[CombinationRisk]:
    """
    检测成分列表中存在的组合风险

    Args:
        ingredients: 标准化 INCI 成分名称列表
    Returns:
        发现的组合风险列表
    """
    lower_ings = {ing.lower() for ing in ingredients}
    found_risks: list[CombinationRisk] = []

    for rule in COMBINATION_RISKS:
        a_match = next((a for a in rule["a_names"] if a in lower_ings), None)
        b_match = next((b for b in rule["b_names"] if b in lower_ings), None)

        if a_match and b_match:
            # 找到原始大小写名称
            a_orig = next((i for i in ingredients if i.lower() == a_match), a_match)
            b_orig = next((i for i in ingredients if i.lower() == b_match), b_match)

            found_risks.append(CombinationRisk(
                ingredient_a=a_orig,
                ingredient_b=b_orig,
                risk_description=rule["risk"],
                severity=rule["severity"],
            ))

    return found_risks


# ─────────────────────────────────────────────
# 单成分分析（优先查 DB，兜底用 JSON KB）
# ─────────────────────────────────────────────

def _get_ingredient_info(inci_name: str) -> dict:
    """从数据库（优先）或 JSON 知识库（兜底）获取成分数据"""
    # 优先查 SQLite
    try:
        details = get_ingredient_details(inci_name)
        if details:
            # 合并 standards 到顶层字段
            standards = details.get("standards", {})
            fda = standards.get("FDA", {})
            gb  = standards.get("GB", {})
            details["fda_status"]        = fda.get("status", "not_listed")
            details["gb_status"]         = gb.get("status", "not_listed")
            details["max_concentration"] = fda.get("max_concentration", "Not specified")
            details["combination_warnings"] = (
                fda.get("combination_warnings", []) or
                gb.get("combination_warnings", [])
            )
            details["concerns"] = fda.get("concerns", details.get("concerns", []))
            return details
    except Exception as e:
        logger.debug(f"[DB查询失败] {inci_name}: {e}")

    # 兜底：JSON 知识库
    kb = _JsonKB.get()
    entry = kb.ingredients.get(inci_name.lower())
    if entry:
        entry = dict(entry)
        entry.setdefault("fda_status", "not_listed")
        entry.setdefault("gb_status", "not_listed")
        entry.setdefault("allergen", False)
        entry.setdefault("combination_warnings", [])
        return entry

    # 未知成分
    return {
        "inci_name": inci_name,
        "cn_name": "",
        "function": [],
        "safety_score": 5,
        "safety_level": "unknown",
        "ewg_score": 0,
        "description": "本地知识库中未收录该成分，建议进一步查询。",
        "concerns": [],
        "fda_status": "not_listed",
        "gb_status": "not_listed",
        "max_concentration": "Not specified",
        "allergen": False,
        "suitable_skin": [],
        "combination_warnings": [],
    }


def _map_risk_level(safety_level: str, safety_score: int,
                    fda_status: str, gb_status: str) -> str:
    """将安全等级映射到风险等级（文档中 Low/Medium/High）"""
    if fda_status in ("Banned", "Prohibited") or gb_status in ("Banned", "Prohibited"):
        return "Critical"
    if safety_level == "prohibited" or safety_score <= 1:
        return "Critical"
    if safety_level == "concern" or safety_score <= 3:
        return "High"
    if safety_level in ("moderate_concern",) or safety_score <= 5:
        return "Medium"
    return "Low"


def analyze_single_ingredient(inci_name: str, kb: Optional[_JsonKB] = None) -> IngredientAnalysis:
    """
    分析单个成分（升级版）

    Args:
        inci_name: INCI 成分名称
    Returns:
        IngredientAnalysis 对象
    """
    info = _get_ingredient_info(inci_name)

    result = IngredientAnalysis(
        inci_name=inci_name,
        cn_name=info.get("cn_name", ""),
        function=info.get("function", []),
        safety_score=info.get("safety_score", 5),
        safety_level=info.get("safety_level", "unknown"),
        ewg_score=info.get("ewg_score", 0),
        description=info.get("description", ""),
        concerns=info.get("concerns", []),
        fda_status=info.get("fda_status", "not_listed"),
        gb_status=info.get("gb_status", "not_listed"),
        max_concentration=info.get("max_concentration", "Not specified"),
        suitable_skin=info.get("suitable_skin", []),
        allergen=bool(info.get("allergen", False)),
        combination_warnings=info.get("combination_warnings", []),
    )

    # 计算风险等级
    result.risk_level = _map_risk_level(
        result.safety_level, result.safety_score,
        result.fda_status, result.gb_status
    )

    # 是否标记
    result.is_flagged = (
        result.fda_status in ("Banned", "Restricted", "Prohibited") or
        result.gb_status in ("Banned", "Restricted", "Prohibited") or
        result.safety_level in ("concern", "moderate_concern", "prohibited") or
        result.safety_score <= 5 or
        result.allergen
    )

    return result


# ─────────────────────────────────────────────
# 肤质适用
# ─────────────────────────────────────────────

SKIN_TYPES = ["all", "dry", "oily", "combination", "sensitive", "acne-prone", "aging"]
SKIN_LABELS_CN = {
    "all": "通用",
    "dry": "干性肌",
    "oily": "油性肌",
    "combination": "混合肌",
    "sensitive": "敏感肌",
    "acne-prone": "痘痘肌",
    "aging": "熟龄肌",
}


def _compute_skin_suitability(analyses: list[IngredientAnalysis]) -> dict:
    skin_scores: dict[str, list[float]] = {s: [] for s in SKIN_TYPES}
    for a in analyses:
        suitable = a.suitable_skin
        if "all" in suitable:
            for s in SKIN_TYPES:
                skin_scores[s].append(a.safety_score)
        else:
            for s in suitable:
                if s in skin_scores:
                    skin_scores[s].append(a.safety_score)
            for s in SKIN_TYPES:
                if s not in suitable and "all" not in suitable and skin_scores[s]:
                    skin_scores[s].append(max(1, a.safety_score - 2))

    result = {}
    for s, scores in skin_scores.items():
        avg = round(sum(scores) / len(scores), 1) if scores else 5.0
        label = "适合" if avg >= 7 else ("一般" if avg >= 5 else "谨慎")
        result[SKIN_LABELS_CN[s]] = {"score": avg, "label": label}
    return result


# ─────────────────────────────────────────────
# 建议生成（Step 2 扩充）
# ─────────────────────────────────────────────

def _generate_recommendations(report: ComplianceReport) -> list[str]:
    recs = []
    flagged_names_lower = {a.inci_name.lower() for a in report.flagged_ingredients}

    # 综合评分
    if report.overall_safety_score >= 8:
        recs.append("✅ 该产品成分整体安全评分优秀，适合日常使用。")
    elif report.overall_safety_score >= 6:
        recs.append("⚠️ 该产品有少量需关注成分，建议敏感肌用户先做局部贴肤测试（耳后/内腕）。")
    else:
        recs.append("🚨 该产品存在多个高风险成分，建议谨慎选购，必要时参考专业皮肤科建议。")

    # 合规警告
    if report.fda_compliance == "prohibited":
        recs.append("🚫 该产品含有 FDA 明确禁用成分，在美国市场销售可能违反21 CFR法规。")
    elif report.fda_compliance == "restricted":
        recs.append("⚠️ 该产品含有 FDA 限制性成分，请核查使用浓度是否符合21 CFR要求。")

    if report.gb_compliance == "prohibited":
        recs.append("🚫 该产品含有中国《化妆品安全技术规范》明确禁用成分，在中国市场销售涉嫌违规。")
    elif report.gb_compliance == "restricted":
        recs.append("⚠️ 该产品含有中国限制性成分，请核查使用浓度合规性。")

    # 组合风险
    for cr in report.combination_risks:
        sev_icon = "🔴" if cr.severity == "High" else ("🟠" if cr.severity == "Medium" else "🟡")
        recs.append(f"{sev_icon} 组合风险 [{cr.ingredient_a} + {cr.ingredient_b}]：{cr.risk_description}")

    # 过敏原
    if report.allergens_found:
        allergen_list = "、".join(report.allergens_found[:5])
        recs.append(f"🌸 含有 {len(report.allergens_found)} 种已知致敏原：{allergen_list}。过敏体质人群请注意。")

    # 成分特定建议
    if "alcohol denat." in flagged_names_lower or "ethanol" in flagged_names_lower:
        recs.append("💧 含有酒精（变性乙醇），干性皮肤或屏障受损者请谨慎使用，建议避开受损部位。")
    if any("paraben" in n for n in flagged_names_lower):
        recs.append("🧪 含有尼泊金酯类防腐剂（Paraben），有内分泌干扰嫌疑，孕妇及婴幼儿建议回避。")
    if any("fragrance" in n or "parfum" in n for n in flagged_names_lower):
        recs.append("🌸 含有香精（Fragrance/Parfum），成分不透明，敏感皮肤及香精过敏人群请避免使用。")
    if "retinol" in flagged_names_lower:
        recs.append("🤰 含有视黄醇（Retinol），孕妇请避免使用；建议晚间使用并配合SPF30+防晒。")
    if "salicylic acid" in flagged_names_lower:
        recs.append("☀️ 含有水杨酸，有光敏感性，日间使用后务必使用宽谱防晒产品。")
    if "sodium benzoate" in flagged_names_lower:
        recs.append("⚗️ 含有苯甲酸钠防腐剂，请避免与高浓度维C产品同时使用，储存时请避光避热。")
    if "triclosan" in flagged_names_lower:
        recs.append("🚫 含有三氯生（Triclosan），该成分已被FDA禁止用于洗手液（2016），请谨慎使用。")
    if any(n in flagged_names_lower for n in ["mercury compounds", "lead", "arsenic"]):
        recs.append("☠️ 检测到重金属类成分（汞/铅/砷），这些是全球性禁用成分，请立即停止使用并向相关机构举报。")
    if "hydroquinone" in flagged_names_lower:
        recs.append("⚠️ 含有氢醌（Hydroquinone），EU已禁止在OTC化妆品中使用；长期使用存在致癌和皮肤色斑风险。")

    return recs


# ─────────────────────────────────────────────
# 核心主函数
# ─────────────────────────────────────────────

HIGHLIGHT_INGREDIENTS = {
    "Niacinamide", "Sodium Hyaluronate", "Hyaluronic Acid",
    "Retinol", "Ascorbic Acid", "Vitamin C", "Adenosine",
    "Centella Asiatica Extract", "Bifida Ferment Lysate",
    "Tocopherol", "Zinc Oxide", "Titanium Dioxide",
    "Salicylic Acid", "Ceramide NP", "Galactomyces Ferment Filtrate"
}


def analyze_product(
    brand: str,
    product_name: str,
    ingredients: list[str],
    save_to_db: bool = True,
) -> ComplianceReport:
    """
    对化妆品进行深度合规性分析（Step 2）

    Args:
        brand:        品牌名称
        product_name: 产品名称
        ingredients:  成分列表
        save_to_db:   是否将结果持久化到数据库
    Returns:
        ComplianceReport 完整分析报告
    """
    report = ComplianceReport(
        brand=brand,
        product_name=product_name,
        total_ingredients=len(ingredients),
    )

    # 1. 单成分分析
    analyses: list[IngredientAnalysis] = [
        analyze_single_ingredient(ing.strip())
        for ing in ingredients
        if ing.strip()
    ]
    report.ingredient_analyses = analyses

    # 2. 标记成分
    report.flagged_ingredients = [a for a in analyses if a.is_flagged]

    # 3. 过敏原汇总
    report.allergens_found = [a.inci_name for a in analyses if a.allergen]

    # 4. 组合风险检测
    report.combination_risks = _check_combination_risks(
        [a.inci_name for a in analyses]
    )

    # 5. 优质成分亮点
    report.safe_highlights = [
        a.inci_name for a in analyses
        if a.inci_name in HIGHLIGHT_INGREDIENTS and not a.is_flagged
    ]

    # 6. 综合安全评分（前5位成分双倍权重）
    scores = [a.safety_score for a in analyses if a.safety_score > 0]
    if scores:
        weighted = scores[:5] * 2 + scores[5:]
        report.overall_safety_score = round(sum(weighted) / len(weighted), 2)
    else:
        report.overall_safety_score = 5.0

    # 7. 安全等级
    s = report.overall_safety_score
    if s >= 8:
        report.overall_safety_level = "safe"
    elif s >= 6:
        report.overall_safety_level = "caution"
    elif s >= 4:
        report.overall_safety_level = "moderate_concern"
    else:
        report.overall_safety_level = "concern"

    # 8. 整体风险等级（文档风格：Low/Medium/High/Critical）
    risk_mapping = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    max_risk = max((risk_mapping.get(a.risk_level, 1) for a in analyses), default=1)
    if report.combination_risks:
        max_combo = max(risk_mapping.get(cr.severity, 1) for cr in report.combination_risks)
        max_risk = max(max_risk, max_combo)
    report.overall_risk_level = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}.get(max_risk, "Low")

    # 9. 合规性汇总
    fda_statuses = [a.fda_status for a in analyses]
    gb_statuses  = [a.gb_status for a in analyses]

    for statuses, attr in [(fda_statuses, "fda_compliance"), (gb_statuses, "gb_compliance")]:
        if any(s in ("Banned", "Prohibited") for s in statuses):
            setattr(report, attr, "prohibited")
        elif any(s in ("Restricted",) for s in statuses):
            setattr(report, attr, "restricted")
        else:
            setattr(report, attr, "compliant")

    # 10. 肤质适用性
    report.skin_suitability = _compute_skin_suitability(analyses)

    # 11. 建议
    report.recommendations = _generate_recommendations(report)

    # 12. 摘要
    flag_count = len(report.flagged_ingredients)
    allergen_count = len(report.allergens_found)
    combo_count = len(report.combination_risks)
    report.summary = (
        f"{brand} · {product_name} 共 {report.total_ingredients} 种成分，"
        f"综合安全评分 {report.overall_safety_score}/10 ({report.overall_safety_level})，"
        f"整体风险: {report.overall_risk_level}，"
        f"标注成分 {flag_count} 种，过敏原 {allergen_count} 种，"
        f"组合风险 {combo_count} 项。"
        f"FDA: {report.fda_compliance} | GB: {report.gb_compliance}。"
    )

    # 13. 数据库持久化
    if save_to_db:
        try:
            product_id = upsert_product(brand, product_name)
            save_product_ingredients(product_id, [a.inci_name for a in analyses])
            report.product_id = product_id
        except Exception as e:
            logger.warning(f"[DB] 持久化失败（不影响分析结果）: {e}")

    return report


def report_to_dict(report: ComplianceReport) -> dict:
    """将 ComplianceReport 转换为可序列化字典"""

    def analysis_to_dict(a: IngredientAnalysis) -> dict:
        return {
            "inci_name": a.inci_name,
            "cn_name": a.cn_name,
            "function": a.function,
            "safety_score": a.safety_score,
            "safety_level": a.safety_level,
            "ewg_score": a.ewg_score,
            "description": a.description,
            "concerns": a.concerns,
            "fda_status": a.fda_status,
            "gb_status": a.gb_status,
            "max_concentration": a.max_concentration,
            "suitable_skin": a.suitable_skin,
            "allergen": a.allergen,
            "combination_warnings": a.combination_warnings,
            "is_flagged": a.is_flagged,
            "risk_level": a.risk_level,
        }

    def combo_to_dict(c: CombinationRisk) -> dict:
        return {
            "ingredient_a": c.ingredient_a,
            "ingredient_b": c.ingredient_b,
            "risk_description": c.risk_description,
            "severity": c.severity,
        }

    return {
        "brand": report.brand,
        "product_name": report.product_name,
        "total_ingredients": report.total_ingredients,
        "overall_safety_score": report.overall_safety_score,
        "overall_safety_level": report.overall_safety_level,
        "overall_risk_level": report.overall_risk_level,
        "fda_compliance": report.fda_compliance,
        "gb_compliance": report.gb_compliance,
        "ingredient_analyses": [analysis_to_dict(a) for a in report.ingredient_analyses],
        "flagged_ingredients": [analysis_to_dict(a) for a in report.flagged_ingredients],
        "allergens_found": report.allergens_found,
        "combination_risks": [combo_to_dict(c) for c in report.combination_risks],
        "safe_highlights": report.safe_highlights,
        "recommendations": report.recommendations,
        "skin_suitability": report.skin_suitability,
        "summary": report.summary,
        "product_id": report.product_id,
    }
