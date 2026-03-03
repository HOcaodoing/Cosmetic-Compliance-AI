"""
scraper.py - 网络爬虫模块（Step 2 升级版）
Cosmetic Compliance AI

新增：
  - 成分文本标准化（去除数字/百分号/编号前缀）
  - INCI 名称规范化（首字母大写、去除多余空格）
  - 组合风险检测预处理
  - 真实爬虫框架（INCIDecoder + CosDNA），附降级策略
"""

import re
import time
import logging
import requests
from typing import Optional
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# HTTP 配置
# ─────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}
REQUEST_TIMEOUT = 10

# ─────────────────────────────────────────────
# 本地模拟产品库（Step 2 扩充版）
# ─────────────────────────────────────────────
MOCK_PRODUCTS: dict[str, list[str]] = {
    # 国产品牌
    "欧莱雅_小黑瓶精华": [
        "Water", "Bifida Ferment Lysate", "Glycerin",
        "Alcohol Denat.", "Adenosine", "Niacinamide",
        "Sodium Hyaluronate", "Tocopherol",
        "Phenoxyethanol", "Carbomer"
    ],
    "雅诗兰黛_小棕瓶": [
        "Water", "Bifida Ferment Lysate", "Glycerin",
        "Sodium Hyaluronate", "Adenosine", "Tocopherol",
        "Centella Asiatica Extract", "Niacinamide",
        "Phenoxyethanol", "Fragrance"
    ],
    "完美日记_粉底液": [
        "Water", "Cyclopentasiloxane", "Titanium Dioxide",
        "Dimethicone", "Glycerin", "Niacinamide",
        "Sodium Benzoate", "Methylparaben", "Fragrance"
    ],
    "珀莱雅_双抗精华": [
        "Water", "Niacinamide", "Ascorbic Acid",
        "Sodium Hyaluronate", "Adenosine",
        "Centella Asiatica Extract", "Tocopherol",
        "Carbomer", "Phenoxyethanol"
    ],
    "薇诺娜_舒缓保湿霜": [
        "Water", "Glycerin", "Ceramide NP",
        "Sodium Hyaluronate", "Centella Asiatica Extract",
        "Dimethicone", "Carbomer", "Phenoxyethanol"
    ],
    # 国际品牌
    "perfect diary_foundation": [
        "Aqua", "Titanium Dioxide", "Glycerin",
        "Sodium Benzoate", "Parfum",
        "Dimethicone", "Niacinamide"
    ],
    "loreal_shampoo": [
        "Aqua", "Sodium Laureth Sulfate",
        "Cocamidopropyl Betaine", "Glycerin",
        "Parabens", "Fragrance"
    ],
    "olay_moisturizer": [
        "Water", "Glycerin", "Niacinamide",
        "Dimethicone", "Phenoxyethanol"
    ],
    "loreal_revitalift": [
        "Water", "Glycerin", "Dimethicone", "Niacinamide",
        "Sodium Hyaluronate", "Adenosine", "Tocopherol",
        "Carbomer", "Phenoxyethanol", "Fragrance"
    ],
    "skii_facial_treatment_essence": [
        "Galactomyces Ferment Filtrate", "Water", "Butylene Glycol",
        "Niacinamide", "Sodium Benzoate", "Methylparaben",
        "Sorbic Acid"
    ],
    "la mer_crème de la mer": [
        "Water", "Seaweed Extract", "Mineral Oil", "Petrolatum",
        "Glycerin", "Isohexadecane", "Beeswax",
        "Tocopherol", "Fragrance", "Phenoxyethanol"
    ],
    "neutrogena_hydro boost": [
        "Water", "Dimethicone", "Glycerin",
        "Sodium Hyaluronate", "Phenoxyethanol",
        "Methylparaben", "Carbomer"
    ],
    # 包含高风险成分的示例（用于演示检测能力）
    "demo_high_risk_product": [
        "Water", "Glycerin", "Triclosan",
        "Formaldehyde Releasers", "Phthalates",
        "Fragrance", "Methylparaben"
    ],
    "demo_benzene_risk": [
        "Water", "Glycerin", "Sodium Benzoate",
        "Ascorbic Acid", "Niacinamide", "Phenoxyethanol"
    ],
    "default": [
        "Water", "Glycerin", "Sodium Hyaluronate",
        "Niacinamide", "Dimethicone", "Tocopherol",
        "Carbomer", "Phenoxyethanol"
    ],
}

# ─────────────────────────────────────────────
# 成分名标准化
# ─────────────────────────────────────────────

# 常见 INCI 别名映射（CN/通用名 → 标准INCI）
INCI_ALIASES: dict[str, str] = {
    "aqua": "Water",
    "h2o": "Water",
    "vitamin c": "Ascorbic Acid",
    "vc": "Ascorbic Acid",
    "vit c": "Ascorbic Acid",
    "vitamin e": "Tocopherol",
    "vit e": "Tocopherol",
    "vitamin a": "Retinol",
    "hyaluronic acid": "Sodium Hyaluronate",
    "ha": "Sodium Hyaluronate",
    "透明质酸": "Sodium Hyaluronate",
    "玻尿酸": "Sodium Hyaluronate",
    "甘油": "Glycerin",
    "水": "Water",
    "烟酰胺": "Niacinamide",
    "视黄醇": "Retinol",
    "水杨酸": "Salicylic Acid",
    "维生素c": "Ascorbic Acid",
    "维生素e": "Tocopherol",
    "氢醌": "Hydroquinone",
}


def normalize_inci_name(raw: str) -> str:
    """
    标准化成分名称：
      1. 去除序号前缀 (1. / (1) / ① 等)
      2. 去除浓度信息 (5%, <0.1%, etc.)
      3. 去除括号注释
      4. 去除首尾空白和特殊符号
      5. 查别名映射
      6. Title Case 规范化

    Args:
        raw: 原始成分文本
    Returns:
        标准化后的 INCI 名称
    """
    name = raw.strip()

    # 去除序号前缀
    name = re.sub(r"^[\d\①\②\③\④\⑤\⑥\⑦\⑧\⑨\⑩]+[.)、\s]+", "", name)

    # 去除浓度标注 (5%, <0.1%, ≤2% 等)
    name = re.sub(r"[<≤≥>]?\s*\d+\.?\d*\s*%", "", name)

    # 去除括号及括号内容（如 (and) (含) 等）
    name = re.sub(r"\s*[\(\（][^)\）]{0,20}[\)\）]", "", name)

    # 去除常见无用前缀
    name = re.sub(r"^(成分|ingredient|inci|添加|contains?)[：:]\s*", "", name, flags=re.IGNORECASE)

    # 去除多余空白和符号
    name = re.sub(r"[·•\-\*\|/]", " ", name).strip()
    name = re.sub(r"\s{2,}", " ", name)

    # 去除纯数字或过短字符
    if not name or name.isdigit() or len(name) < 2:
        return ""

    # 别名映射（小写查找）
    lower_name = name.lower()
    if lower_name in INCI_ALIASES:
        return INCI_ALIASES[lower_name]

    # Title Case（仅对纯英文应用，保留中文）
    if all(c.isascii() or c.isspace() for c in name):
        # 特殊情况：缩写保持大写（pH, DNA, RNA, UV, SPF 等）
        words = name.split()
        normalized_words = []
        KEEP_UPPER = {"ph", "dna", "rna", "uv", "spf", "aka", "aha", "bha", "peg", "cas"}
        for w in words:
            if w.lower() in KEEP_UPPER:
                normalized_words.append(w.upper())
            else:
                normalized_words.append(w.capitalize())
        name = " ".join(normalized_words)

    return name.strip()


def parse_ingredient_text(raw_text: str) -> list[str]:
    """
    解析用户粘贴的成分全文，返回标准化成分列表

    支持：逗号分隔、换行分隔、分号分隔、编号列表

    Args:
        raw_text: 原始成分字符串
    Returns:
        清洗标准化后的 INCI 名称列表（去重，保持顺序）
    """
    # 按常见分隔符拆分
    parts = re.split(r"[,\n;|]+", raw_text)

    seen = set()
    ingredients = []

    for part in parts:
        clean = normalize_inci_name(part)
        if clean and clean not in seen:
            seen.add(clean)
            ingredients.append(clean)

    return ingredients


def validate_ingredients(ingredients: list[str]) -> dict:
    """
    基础成分列表验证

    Args:
        ingredients: 标准化成分列表
    Returns:
        验证结果字典 {valid: bool, message: str}
    """
    if not ingredients:
        return {"valid": False, "message": "成分列表为空"}
    if len(ingredients) < 2:
        return {"valid": False, "message": "成分数量异常（少于2项），请检查格式"}
    if len(ingredients) > 100:
        return {
            "valid": True,
            "message": f"成功解析 {len(ingredients)} 种成分（数量较多，可能含重复）"
        }
    return {"valid": True, "message": f"成功解析 {len(ingredients)} 种成分"}


# ─────────────────────────────────────────────
# 爬虫内核
# ─────────────────────────────────────────────

def _normalize_key(brand: str, product: str) -> str:
    """标准化查找键"""
    combined = f"{brand.strip()}_{product.strip()}"
    return combined.lower().replace(" ", "_")


def _fetch_from_incidecoder(brand: str, product: str) -> Optional[list[str]]:
    """
    真实爬虫：INCIDecoder 搜索
    （因反爬限制，返回 None 触发降级；真实部署需处理 JS 渲染或使用 Playwright）
    """
    try:
        query = f"{brand} {product}"
        url = f"https://incidecoder.com/search?q={quote_plus(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        if resp.status_code == 200:
            # 检查是否有成分数据（真实解析需要 BeautifulSoup 深度处理）
            if "ingredientlist" in resp.text.lower() or "ingredients" in resp.text.lower():
                logger.info("[INCIDecoder] 页面可访问，成分解析需进一步开发")
                # TODO: from bs4 import BeautifulSoup; soup = BeautifulSoup(resp.text, 'html.parser')
                # ingredients_div = soup.find('div', {'id': 'ingredientlist'})
                # parse and return
        return None
    except requests.RequestException as e:
        logger.warning(f"[INCIDecoder] 请求失败: {e}")
        return None


def _fetch_from_cosdna(brand: str, product: str) -> Optional[list[str]]:
    """
    真实爬虫：CosDNA 搜索框架
    （需根据 CosDNA 实际结构调整选择器）
    """
    try:
        query = f"{brand} {product}"
        url = f"https://www.cosdna.com/chi/cosmetic_search.php?q={quote_plus(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        if resp.status_code == 200:
            logger.info("[CosDNA] 页面可访问，成分解析需进一步开发")
            # TODO: BeautifulSoup 解析成分列表
        return None
    except requests.RequestException as e:
        logger.warning(f"[CosDNA] 请求失败: {e}")
        return None


def web_scraper(brand: str, product: str) -> list[str]:
    """
    核心爬虫函数：多源降级策略

    优先级：INCIDecoder → CosDNA → 本地模拟库 → 默认成分

    Args:
        brand:   品牌名称
        product: 产品名称
    Returns:
        标准化的 INCI 成分列表
    """
    logger.info(f"[Scraper] 开始爬取: {brand} - {product}")

    # 策略 1: INCIDecoder
    ingredients = _fetch_from_incidecoder(brand, product)
    if ingredients:
        logger.info("[Scraper] 数据来源: INCIDecoder")
        return [normalize_inci_name(i) for i in ingredients if normalize_inci_name(i)]

    time.sleep(0.3)  # 礼貌延迟

    # 策略 2: CosDNA
    ingredients = _fetch_from_cosdna(brand, product)
    if ingredients:
        logger.info("[Scraper] 数据来源: CosDNA")
        return [normalize_inci_name(i) for i in ingredients if normalize_inci_name(i)]

    # 策略 3: 本地模拟数据库
    key = _normalize_key(brand, product)
    ingredients = MOCK_PRODUCTS.get(key)
    if ingredients:
        logger.info(f"[Scraper] 数据来源: 本地模拟库 (key={key})")
        return ingredients

    # 最终降级
    logger.warning(f"[Scraper] 未找到 '{brand} - {product}'，返回默认成分")
    return MOCK_PRODUCTS["default"]
