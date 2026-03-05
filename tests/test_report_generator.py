"""
tests/test_report_generator.py - AI 报告生成模块单元测试
对应文档第三步：AI 分析报告生成模块

覆盖以下函数：
- generate_report_prompt()
- generate_compliance_report()   （无 API Key 的降级路径）
- generate_risk_assessment()     （规则引擎，含浓度参数）
- build_detailed_analysis()
- detect_interaction_warnings()
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from report_generator import (
    generate_report_prompt,
    generate_compliance_report,
    generate_risk_assessment,
    build_detailed_analysis,
    detect_interaction_warnings,
)


# ─────────────────────────────────────────────
# 公共 Fixture
# ─────────────────────────────────────────────

@pytest.fixture
def sample_analysis_result():
    """模拟 analyzer.report_to_dict() 的返回值"""
    return {
        "brand":                "雅诗兰黛",
        "product_name":         "小棕瓶精华",
        "total_ingredients":    5,
        "overall_safety_score": 7.5,
        "overall_safety_level": "caution",
        "fda_compliance":       "compliant",
        "gb_compliance":        "restricted",
        "summary":              "雅诗兰黛 · 小棕瓶精华 共检测到 5 种成分，综合安全评分 7.5/10。",
        "recommendations":      ["⚠️ 含少量需关注成分，敏感肌请先做贴肤测试。"],
        "safe_highlights":      ["Niacinamide", "Sodium Hyaluronate"],
        "skin_suitability": {
            "通用":  {"score": 7.5, "label": "适合"},
            "敏感肌": {"score": 6.0, "label": "一般"},
        },
        "ingredient_analyses": [
            {
                "inci_name":    "Water",
                "cn_name":      "水",
                "function":     ["溶剂"],
                "safety_score": 10,
                "safety_level": "safe",
                "ewg_score":    1,
                "description":  "最常见的化妆品基础成分。",
                "concerns":     [],
                "fda_status":   "not_listed",
                "gb_status":    "not_listed",
                "suitable_skin": ["all"],
                "is_flagged":   False,
            },
            {
                "inci_name":    "Niacinamide",
                "cn_name":      "烟酰胺",
                "function":     ["美白", "抗炎"],
                "safety_score": 9,
                "safety_level": "safe",
                "ewg_score":    2,
                "description":  "维生素B3，多效活性成分。",
                "concerns":     [],
                "fda_status":   "not_listed",
                "gb_status":    "not_listed",
                "suitable_skin": ["all"],
                "is_flagged":   False,
            },
            {
                "inci_name":    "Sodium Hyaluronate",
                "cn_name":      "透明质酸钠",
                "function":     ["保湿"],
                "safety_score": 9,
                "safety_level": "safe",
                "ewg_score":    1,
                "description":  "透明质酸钠，强效保湿。",
                "concerns":     [],
                "fda_status":   "not_listed",
                "gb_status":    "not_listed",
                "suitable_skin": ["all"],
                "is_flagged":   False,
            },
            {
                "inci_name":    "Methylparaben",
                "cn_name":      "尼泊金甲酯",
                "function":     ["防腐剂"],
                "safety_score": 4,
                "safety_level": "moderate_concern",
                "ewg_score":    4,
                "description":  "常见防腐剂，有内分泌干扰嫌疑。",
                "concerns":     ["可能具有内分泌干扰性", "孕妇及婴幼儿建议避免"],
                "fda_status":   "not_listed",
                "gb_status":    "restricted",
                "suitable_skin": [],
                "is_flagged":   True,
            },
            {
                "inci_name":    "Fragrance",
                "cn_name":      "香精",
                "function":     ["赋香"],
                "safety_score": 3,
                "safety_level": "concern",
                "ewg_score":    8,
                "description":  "混合香精，致敏风险高。",
                "concerns":     ["高致敏风险", "成分不透明"],
                "fda_status":   "not_listed",
                "gb_status":    "not_listed",
                "suitable_skin": [],
                "is_flagged":   True,
            },
        ],
        "flagged_ingredients": [
            {
                "inci_name":    "Methylparaben",
                "cn_name":      "尼泊金甲酯",
                "function":     ["防腐剂"],
                "safety_score": 4,
                "safety_level": "moderate_concern",
                "ewg_score":    4,
                "description":  "常见防腐剂，有内分泌干扰嫌疑。",
                "concerns":     ["可能具有内分泌干扰性", "孕妇及婴幼儿建议避免"],
                "fda_status":   "not_listed",
                "gb_status":    "restricted",
                "suitable_skin": [],
                "is_flagged":   True,
            },
            {
                "inci_name":    "Fragrance",
                "cn_name":      "香精",
                "function":     ["赋香"],
                "safety_score": 3,
                "safety_level": "concern",
                "ewg_score":    8,
                "description":  "混合香精，致敏风险高。",
                "concerns":     ["高致敏风险", "成分不透明"],
                "fda_status":   "not_listed",
                "gb_status":    "not_listed",
                "suitable_skin": [],
                "is_flagged":   True,
            },
        ],
    }


# ─────────────────────────────────────────────
# generate_report_prompt
# ─────────────────────────────────────────────

class TestGenerateReportPrompt:
    def test_contains_brand_and_product(self, sample_analysis_result):
        prompt = generate_report_prompt(sample_analysis_result)
        assert "雅诗兰黛" in prompt
        assert "小棕瓶精华" in prompt

    def test_contains_risk_ingredients(self, sample_analysis_result):
        prompt = generate_report_prompt(sample_analysis_result)
        assert "Methylparaben" in prompt or "Fragrance" in prompt

    def test_contains_safety_score(self, sample_analysis_result):
        prompt = generate_report_prompt(sample_analysis_result)
        assert "7.5" in prompt

    def test_contains_report_structure_keywords(self, sample_analysis_result):
        prompt = generate_report_prompt(sample_analysis_result)
        assert "总体评价" in prompt
        assert "风险成分" in prompt
        assert "肤质" in prompt

    def test_prompt_is_string(self, sample_analysis_result):
        prompt = generate_report_prompt(sample_analysis_result)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_empty_analysis_result(self):
        """空数据不应抛出异常"""
        prompt = generate_report_prompt({})
        assert isinstance(prompt, str)
        assert "未知品牌" in prompt


# ─────────────────────────────────────────────
# generate_risk_assessment
# ─────────────────────────────────────────────

class TestGenerateRiskAssessment:
    def test_prohibited_ingredient_is_high_risk(self):
        result = generate_risk_assessment(
            "HarmfulXYZ", safety_score=2, concerns=[],
            fda_status="prohibited", gb_status="not_listed"
        )
        assert result["risk_level"] == "high"
        assert "HarmfulXYZ" == result["ingredient"]

    def test_restricted_ingredient_is_medium_risk(self):
        result = generate_risk_assessment(
            "Methylparaben", safety_score=4, concerns=["内分泌干扰"],
            fda_status="not_listed", gb_status="restricted"
        )
        assert result["risk_level"] == "medium"
        assert result["recommendation"] != ""

    def test_high_safety_score_is_low_risk(self):
        result = generate_risk_assessment(
            "Water", safety_score=9, concerns=[],
            fda_status="not_listed", gb_status="not_listed"
        )
        assert result["risk_level"] == "low"

    def test_low_safety_score_is_high_risk(self):
        result = generate_risk_assessment(
            "DangerousX", safety_score=2, concerns=["severe toxicity"],
            fda_status="not_listed", gb_status="not_listed"
        )
        assert result["risk_level"] == "high"

    def test_return_structure(self):
        result = generate_risk_assessment("TestIngredient", safety_score=5, concerns=[])
        required_keys = {"ingredient", "risk_level", "risk_label", "reason", "recommendation", "concerns"}
        assert required_keys.issubset(result.keys())

    # ── 浓度参数测试（文档新增要求） ──

    def test_concentration_over_limit_upgrades_to_high_risk(self):
        """浓度超限应直接升为高风险"""
        result = generate_risk_assessment(
            "Phenoxyethanol", safety_score=7, concerns=[],
            fda_status="not_listed", gb_status="not_listed",
            concentration=2.0   # 超过 1.0% 限值
        )
        assert result["risk_level"] == "high"
        assert "concentration_info" in result
        assert result["concentration_info"]["over_limit"] is True

    def test_concentration_within_limit_no_upgrade(self):
        """浓度在限值内，不强制升为高风险"""
        result = generate_risk_assessment(
            "Phenoxyethanol", safety_score=7, concerns=[],
            fda_status="not_listed", gb_status="not_listed",
            concentration=0.5   # 低于 1.0% 限值
        )
        assert result["concentration_info"]["over_limit"] is False
        # 安全评分 7 对应 medium 风险
        assert result["risk_level"] in ("low", "medium")

    def test_concentration_none_no_concentration_info(self):
        """未传 concentration 时结果中不应有 concentration_info 字段"""
        result = generate_risk_assessment("Water", safety_score=9, concerns=[])
        assert "concentration_info" not in result

    def test_backward_compatible_without_concentration(self):
        """旧调用方式（无 concentration 参数）应仍然正常工作"""
        result = generate_risk_assessment(
            ingredient_name="Fragrance",
            safety_score=3,
            concerns=["高致敏风险"],
        )
        assert result["risk_level"] == "high"
        assert isinstance(result["concerns"], list)


# ─────────────────────────────────────────────
# detect_interaction_warnings
# ─────────────────────────────────────────────

class TestDetectInteractionWarnings:
    def test_sodium_benzoate_vitamin_c(self):
        warnings = detect_interaction_warnings(["Sodium Benzoate", "Vitamin C", "Water"])
        assert len(warnings) >= 1
        assert any("苯甲酸钠" in w or "苯" in w for w in warnings)

    def test_retinol_salicylic_acid(self):
        warnings = detect_interaction_warnings(["Retinol", "Salicylic Acid"])
        assert len(warnings) >= 1

    def test_no_interaction(self):
        warnings = detect_interaction_warnings(["Water", "Glycerin", "Niacinamide"])
        assert warnings == []

    def test_case_insensitive(self):
        warnings = detect_interaction_warnings(["sodium benzoate", "vitamin c"])
        assert len(warnings) >= 1

    def test_empty_list(self):
        warnings = detect_interaction_warnings([])
        assert warnings == []

    def test_single_ingredient(self):
        warnings = detect_interaction_warnings(["Retinol"])
        assert warnings == []

    def test_multiple_interactions_detected(self):
        """含多组风险组合"""
        warnings = detect_interaction_warnings([
            "Sodium Benzoate", "Vitamin C",
            "Retinol", "Salicylic Acid",
        ])
        assert len(warnings) >= 2


# ─────────────────────────────────────────────
# build_detailed_analysis
# ─────────────────────────────────────────────

class TestBuildDetailedAnalysis:
    def test_structure_keys(self, sample_analysis_result):
        result = build_detailed_analysis(sample_analysis_result)
        assert "safe_ingredients" in result
        assert "risk_ingredients" in result
        assert "interaction_warnings" in result

    def test_safe_ingredients_are_correct(self, sample_analysis_result):
        result = build_detailed_analysis(sample_analysis_result)
        safe_names = [i["name"] for i in result["safe_ingredients"]]
        assert "Water" in safe_names
        assert "Niacinamide" in safe_names
        # 风险成分不应出现在安全列表中
        assert "Methylparaben" not in safe_names
        assert "Fragrance" not in safe_names

    def test_risk_ingredients_are_correct(self, sample_analysis_result):
        result = build_detailed_analysis(sample_analysis_result)
        risk_names = [i["name"] for i in result["risk_ingredients"]]
        assert "Methylparaben" in risk_names
        assert "Fragrance" in risk_names

    def test_risk_ingredient_has_required_fields(self, sample_analysis_result):
        result = build_detailed_analysis(sample_analysis_result)
        for ri in result["risk_ingredients"]:
            assert "name" in ri
            assert "risk_level" in ri
            assert "reason" in ri
            assert "recommendation" in ri

    def test_safe_ingredient_has_required_fields(self, sample_analysis_result):
        result = build_detailed_analysis(sample_analysis_result)
        for si in result["safe_ingredients"]:
            assert "name" in si
            assert "function" in si
            assert "safety_level" in si

    def test_empty_analysis(self):
        result = build_detailed_analysis({})
        assert result["safe_ingredients"] == []
        assert result["risk_ingredients"] == []
        assert result["interaction_warnings"] == []


# ─────────────────────────────────────────────
# generate_compliance_report（降级路径）
# ─────────────────────────────────────────────

class TestGenerateComplianceReport:
    def test_no_api_key_returns_failure(self, sample_analysis_result):
        """无 API Key 时应优雅降级，success=False"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")
        assert result["success"] is False
        assert "ANTHROPIC_API_KEY" in result.get("error", "")

    def test_no_api_key_returns_required_keys(self, sample_analysis_result):
        """无 API Key 时返回结构仍包含所有必要字段"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")

        required = {
            "product_info", "summary", "detailed_analysis",
            "report_content", "final_recommendation",
            "generated_at", "version", "success",
        }
        assert required.issubset(result.keys())

    def test_no_api_key_product_info_correct(self, sample_analysis_result):
        """product_info 字段品牌名称应正确"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")
        assert result["product_info"]["brand"] == "雅诗兰黛"
        assert result["product_info"]["product_name"] == "小棕瓶精华"

    def test_no_api_key_detailed_analysis_populated(self, sample_analysis_result):
        """即使没有 API Key，detailed_analysis 也应由规则引擎填充"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")
        da = result["detailed_analysis"]
        assert len(da["safe_ingredients"]) > 0
        assert len(da["risk_ingredients"]) > 0

    def test_no_api_key_version_is_1_0(self, sample_analysis_result):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")
        assert result["version"] == "1.0"

    def test_report_content_is_string(self, sample_analysis_result):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            result = generate_compliance_report(sample_analysis_result, api_key="")
        assert isinstance(result["report_content"], str)
        assert len(result["report_content"]) > 0

    def test_with_mocked_claude_api(self, sample_analysis_result):
        """模拟 Claude API 成功调用"""
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="## 模拟报告\n这是一份模拟的合规性报告。")]
        mock_message.usage.input_tokens  = 500
        mock_message.usage.output_tokens = 200

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message

        mock_anthropic_module = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            result = generate_compliance_report(
                sample_analysis_result, api_key="fake-key-for-test"
            )

        assert result["success"] is True
        assert "模拟报告" in result["report_content"]
        assert result["tokens_used"]["input"]  == 500
        assert result["tokens_used"]["output"] == 200
        assert result["model"] == "claude-sonnet-4-6"
        # 成功时结构字段也应完整
        assert "detailed_analysis" in result
        assert "final_recommendation" in result
        assert "summary" in result

    def test_import_error_returns_failure(self, sample_analysis_result):
        """anthropic 包不存在时优雅降级"""
        with patch.dict("sys.modules", {"anthropic": None}):
            result = generate_compliance_report(
                sample_analysis_result, api_key="fake-key"
            )
        assert result["success"] is False
        assert "detailed_analysis" in result
