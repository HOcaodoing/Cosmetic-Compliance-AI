"""
database.py - SQLite 数据库管理模块 (Step 2)
Cosmetic Compliance AI

实现文档中定义的四张核心表：
  - products            : 产品基本信息
  - ingredients         : 成分标准库（CAS、功能）
  - product_ingredients : 产品-成分多对多关联
  - safety_standards    : 法规安全标准（FDA / GB / EU）

同时提供数据导入、查询、更新的完整 API。
"""

import json
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "cosmetic_compliance.db"
INGREDIENTS_JSON = DATA_DIR / "ingredients_db.json"

# ─────────────────────────────────────────────
# 数据库连接上下文管理器
# ─────────────────────────────────────────────

@contextmanager
def get_connection(db_path: Path = DB_PATH):
    """线程安全的数据库连接上下文管理器"""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # 支持列名访问
    conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
    conn.execute("PRAGMA journal_mode = WAL") # 提高并发性能
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
# 建表 DDL
# ─────────────────────────────────────────────

DDL_STATEMENTS = [
    # 1. 产品表
    """
    CREATE TABLE IF NOT EXISTS products (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        brand        TEXT    NOT NULL,
        name         TEXT    NOT NULL,
        category     TEXT    DEFAULT 'Unknown',
        source       TEXT    DEFAULT 'user_input',
        created_at   TEXT    DEFAULT (datetime('now','localtime')),
        UNIQUE(brand, name)
    )
    """,

    # 2. 标准成分库
    """
    CREATE TABLE IF NOT EXISTS ingredients (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        inci_name    TEXT    NOT NULL UNIQUE,
        cn_name      TEXT,
        cas_number   TEXT,
        function     TEXT,        -- JSON array string
        safety_score INTEGER DEFAULT 5,
        safety_level TEXT    DEFAULT 'unknown',
        ewg_score    INTEGER DEFAULT 0,
        description  TEXT,
        allergen     INTEGER DEFAULT 0,   -- 0/1 boolean
        created_at   TEXT    DEFAULT (datetime('now','localtime'))
    )
    """,

    # 3. 产品-成分关联表
    """
    CREATE TABLE IF NOT EXISTS product_ingredients (
        product_id      INTEGER NOT NULL,
        ingredient_id   INTEGER NOT NULL,
        concentration   TEXT    DEFAULT 'Not disclosed',
        position        INTEGER DEFAULT 0,   -- INCI列表中的位置（越前浓度越高）
        PRIMARY KEY (product_id, ingredient_id),
        FOREIGN KEY (product_id)    REFERENCES products(id)    ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
    )
    """,

    # 4. 安全标准表（FDA / GB / EU）
    """
    CREATE TABLE IF NOT EXISTS safety_standards (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id    INTEGER NOT NULL,
        standard_type    TEXT    NOT NULL,   -- FDA / GB / EU
        status           TEXT    NOT NULL,   -- Approved / Restricted / Banned
        max_concentration TEXT   DEFAULT 'Not specified',
        warning          TEXT,
        concerns         TEXT,               -- JSON array string
        combination_warnings TEXT,           -- JSON array string
        updated_at       TEXT    DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
    )
    """,

    # 5. 查询历史（替代 cache.py 的 SQLite 部分）
    """
    CREATE TABLE IF NOT EXISTS query_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id   INTEGER,
        brand        TEXT,
        product      TEXT,
        queried_at   TEXT    DEFAULT (datetime('now','localtime')),
        source       TEXT,
        result_json  TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
    )
    """,
]

# 索引
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_ingredients_inci ON ingredients(inci_name)",
    "CREATE INDEX IF NOT EXISTS idx_safety_ingredient ON safety_standards(ingredient_id)",
    "CREATE INDEX IF NOT EXISTS idx_pi_product ON product_ingredients(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_history_queried ON query_history(queried_at DESC)",
]


def init_database(db_path: Path = DB_PATH) -> None:
    """
    初始化数据库：创建所有表和索引，并从 JSON 知识库导入成分数据
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        for ddl in DDL_STATEMENTS:
            conn.execute(ddl)
        for idx in INDEX_STATEMENTS:
            conn.execute(idx)

    logger.info(f"[DB] 数据库初始化完成: {db_path}")

    # 从 JSON 知识库导入成分数据
    _import_ingredients_from_json(db_path)


def _import_ingredients_from_json(db_path: Path = DB_PATH) -> int:
    """
    从 ingredients_db.json 批量导入成分和安全标准数据

    Returns:
        导入的新成分数量
    """
    if not INGREDIENTS_JSON.exists():
        logger.warning(f"[DB] 找不到知识库文件: {INGREDIENTS_JSON}")
        return 0

    with open(INGREDIENTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    ingredients = data.get("ingredients", [])
    imported = 0

    with get_connection(db_path) as conn:
        for item in ingredients:
            # 检查是否已存在
            existing = conn.execute(
                "SELECT id FROM ingredients WHERE inci_name = ?",
                (item["inci_name"],)
            ).fetchone()

            if existing:
                continue

            # 插入成分基础数据
            conn.execute("""
                INSERT INTO ingredients
                    (inci_name, cn_name, cas_number, function, safety_score,
                     safety_level, ewg_score, description, allergen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["inci_name"],
                item.get("cn_name", ""),
                item.get("cas", ""),
                json.dumps(item.get("function", []), ensure_ascii=False),
                item.get("safety_score", 5),
                item.get("safety_level", "unknown"),
                item.get("ewg_score", 0),
                item.get("description", ""),
                1 if item.get("allergen") else 0,
            ))

            # 获取新插入的 ID
            ing_id = conn.execute(
                "SELECT id FROM ingredients WHERE inci_name = ?",
                (item["inci_name"],)
            ).fetchone()["id"]

            # 插入 FDA 安全标准
            fda_status = item.get("fda_status", "Approved")
            conn.execute("""
                INSERT INTO safety_standards
                    (ingredient_id, standard_type, status, max_concentration,
                     warning, concerns, combination_warnings)
                VALUES (?, 'FDA', ?, ?, ?, ?, ?)
            """, (
                ing_id,
                fda_status,
                item.get("max_concentration", "Not specified"),
                "; ".join(item.get("concerns", [])),
                json.dumps(item.get("concerns", []), ensure_ascii=False),
                json.dumps(item.get("combination_warnings", []), ensure_ascii=False),
            ))

            # 插入 GB（中国）标准（如有）
            gb_status = item.get("gb_status", "")
            if gb_status:
                conn.execute("""
                    INSERT INTO safety_standards
                        (ingredient_id, standard_type, status, max_concentration,
                         warning, concerns, combination_warnings)
                    VALUES (?, 'GB', ?, ?, ?, ?, ?)
                """, (
                    ing_id,
                    gb_status,
                    item.get("max_concentration", "Not specified"),
                    "; ".join(item.get("concerns", [])),
                    json.dumps(item.get("concerns", []), ensure_ascii=False),
                    json.dumps(item.get("combination_warnings", []), ensure_ascii=False),
                ))

            imported += 1

    if imported:
        logger.info(f"[DB] 成功导入 {imported} 种新成分")
    return imported


# ─────────────────────────────────────────────
# 产品相关操作
# ─────────────────────────────────────────────

def upsert_product(brand: str, product: str,
                   category: str = "Unknown",
                   source: str = "user_input",
                   db_path: Path = DB_PATH) -> int:
    """
    插入或更新产品记录

    Returns:
        产品 ID
    """
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO products (brand, name, category, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(brand, name) DO UPDATE SET
                category = excluded.category,
                source   = excluded.source
        """, (brand, product, category, source))

        row = conn.execute(
            "SELECT id FROM products WHERE brand = ? AND name = ?",
            (brand, product)
        ).fetchone()
        return row["id"]


def save_product_ingredients(product_id: int,
                              ingredients: list[str],
                              db_path: Path = DB_PATH) -> None:
    """
    保存产品的成分列表到关联表（position = INCI列表顺序，越靠前浓度越高）
    """
    with get_connection(db_path) as conn:
        # 清除旧关联
        conn.execute(
            "DELETE FROM product_ingredients WHERE product_id = ?",
            (product_id,)
        )

        for pos, inci_name in enumerate(ingredients):
            ing_name = inci_name.strip()
            # 查找成分 ID（不区分大小写）
            row = conn.execute(
                "SELECT id FROM ingredients WHERE LOWER(inci_name) = LOWER(?)",
                (ing_name,)
            ).fetchone()

            if not row:
                # 动态插入未知成分
                conn.execute("""
                    INSERT OR IGNORE INTO ingredients
                        (inci_name, safety_level, safety_score)
                    VALUES (?, 'unknown', 5)
                """, (ing_name,))
                row = conn.execute(
                    "SELECT id FROM ingredients WHERE LOWER(inci_name) = LOWER(?)",
                    (ing_name,)
                ).fetchone()

            if row:
                conn.execute("""
                    INSERT OR REPLACE INTO product_ingredients
                        (product_id, ingredient_id, position)
                    VALUES (?, ?, ?)
                """, (product_id, row["id"], pos))


def get_product_with_ingredients(brand: str, product: str,
                                  db_path: Path = DB_PATH) -> dict | None:
    """
    查询产品的完整成分和安全数据
    """
    with get_connection(db_path) as conn:
        prod = conn.execute(
            "SELECT * FROM products WHERE brand = ? AND name = ?",
            (brand, product)
        ).fetchone()

        if not prod:
            return None

        product_id = prod["id"]

        rows = conn.execute("""
            SELECT
                i.inci_name, i.cn_name, i.cas_number, i.function,
                i.safety_score, i.safety_level, i.ewg_score,
                i.description, i.allergen,
                pi.position, pi.concentration,
                GROUP_CONCAT(ss.standard_type || ':' || ss.status, '|') AS compliance_summary,
                ss.warning, ss.concerns, ss.combination_warnings,
                ss.max_concentration
            FROM product_ingredients pi
            JOIN ingredients i ON i.id = pi.ingredient_id
            LEFT JOIN safety_standards ss ON ss.ingredient_id = i.id
            WHERE pi.product_id = ?
            GROUP BY i.id
            ORDER BY pi.position
        """, (product_id,)).fetchall()

        ingredients_list = []
        for r in rows:
            try:
                funcs = json.loads(r["function"]) if r["function"] else []
            except (json.JSONDecodeError, TypeError):
                funcs = []
            try:
                concerns = json.loads(r["concerns"]) if r["concerns"] else []
            except (json.JSONDecodeError, TypeError):
                concerns = []
            try:
                combo_warnings = json.loads(r["combination_warnings"]) if r["combination_warnings"] else []
            except (json.JSONDecodeError, TypeError):
                combo_warnings = []

            ingredients_list.append({
                "inci_name": r["inci_name"],
                "cn_name": r["cn_name"] or "",
                "cas_number": r["cas_number"] or "",
                "function": funcs,
                "safety_score": r["safety_score"],
                "safety_level": r["safety_level"],
                "ewg_score": r["ewg_score"],
                "description": r["description"] or "",
                "allergen": bool(r["allergen"]),
                "position": r["position"],
                "concentration": r["concentration"] or "Not disclosed",
                "compliance_summary": r["compliance_summary"] or "",
                "warning": r["warning"] or "",
                "concerns": concerns,
                "combination_warnings": combo_warnings,
                "max_concentration": r["max_concentration"] or "Not specified",
            })

        return {
            "id": product_id,
            "brand": prod["brand"],
            "name": prod["name"],
            "category": prod["category"],
            "created_at": prod["created_at"],
            "ingredients": ingredients_list,
        }


# ─────────────────────────────────────────────
# 成分查询
# ─────────────────────────────────────────────

def get_ingredient_details(inci_name: str,
                            db_path: Path = DB_PATH) -> dict | None:
    """
    查询单个成分的完整安全信息（含所有法规标准）
    """
    with get_connection(db_path) as conn:
        ing = conn.execute(
            "SELECT * FROM ingredients WHERE LOWER(inci_name) = LOWER(?)",
            (inci_name,)
        ).fetchone()

        if not ing:
            return None

        standards = conn.execute(
            "SELECT * FROM safety_standards WHERE ingredient_id = ?",
            (ing["id"],)
        ).fetchall()

        stds = {}
        for s in standards:
            try:
                concerns = json.loads(s["concerns"]) if s["concerns"] else []
            except (json.JSONDecodeError, TypeError):
                concerns = []
            try:
                combo = json.loads(s["combination_warnings"]) if s["combination_warnings"] else []
            except (json.JSONDecodeError, TypeError):
                combo = []

            stds[s["standard_type"]] = {
                "status": s["status"],
                "max_concentration": s["max_concentration"],
                "warning": s["warning"],
                "concerns": concerns,
                "combination_warnings": combo,
            }

        try:
            funcs = json.loads(ing["function"]) if ing["function"] else []
        except (json.JSONDecodeError, TypeError):
            funcs = []

        return {
            "id": ing["id"],
            "inci_name": ing["inci_name"],
            "cn_name": ing["cn_name"] or "",
            "cas_number": ing["cas_number"] or "",
            "function": funcs,
            "safety_score": ing["safety_score"],
            "safety_level": ing["safety_level"],
            "ewg_score": ing["ewg_score"],
            "description": ing["description"] or "",
            "allergen": bool(ing["allergen"]),
            "standards": stds,
        }


def search_ingredients(keyword: str, limit: int = 20,
                       db_path: Path = DB_PATH) -> list[dict]:
    """
    按 INCI 名或中文名模糊搜索成分

    Returns:
        成分字典列表
    """
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT inci_name, cn_name, safety_score, safety_level, ewg_score
            FROM ingredients
            WHERE LOWER(inci_name) LIKE LOWER(?) OR cn_name LIKE ?
            ORDER BY safety_score DESC
            LIMIT ?
        """, (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()

        return [dict(r) for r in rows]


def get_allergens(db_path: Path = DB_PATH) -> list[str]:
    """返回所有致敏原成分名称"""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT inci_name FROM ingredients WHERE allergen = 1"
        ).fetchall()
        return [r["inci_name"] for r in rows]


def get_banned_ingredients(standard: str = "FDA",
                            db_path: Path = DB_PATH) -> list[dict]:
    """
    获取指定法规下的全部禁用成分

    Args:
        standard: 'FDA' | 'GB' | 'EU'
    """
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT i.inci_name, i.cn_name, ss.warning
            FROM safety_standards ss
            JOIN ingredients i ON i.id = ss.ingredient_id
            WHERE ss.standard_type = ? AND ss.status IN ('Banned', 'Prohibited')
        """, (standard,)).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 查询历史（升级版）
# ─────────────────────────────────────────────

def save_query_history_db(brand: str, product: str,
                           product_id: int | None,
                           source: str,
                           result: dict,
                           db_path: Path = DB_PATH) -> None:
    """保存一次查询记录到数据库"""
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO query_history (product_id, brand, product, source, result_json)
            VALUES (?, ?, ?, ?, ?)
        """, (
            product_id,
            brand,
            product,
            source,
            json.dumps(result, ensure_ascii=False),
        ))


def get_query_history_db(limit: int = 20,
                          db_path: Path = DB_PATH) -> list[dict]:
    """获取最近查询历史"""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT brand, product, queried_at, source
            FROM query_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 数据库状态信息
# ─────────────────────────────────────────────

def get_db_stats(db_path: Path = DB_PATH) -> dict:
    """返回数据库统计信息"""
    if not db_path.exists():
        return {"initialized": False}

    with get_connection(db_path) as conn:
        products_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        ingredients_count = conn.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        standards_count = conn.execute("SELECT COUNT(*) FROM safety_standards").fetchone()[0]
        history_count = conn.execute("SELECT COUNT(*) FROM query_history").fetchone()[0]
        allergens_count = conn.execute(
            "SELECT COUNT(*) FROM ingredients WHERE allergen = 1"
        ).fetchone()[0]
        banned_count = conn.execute(
            "SELECT COUNT(*) FROM safety_standards WHERE status IN ('Banned', 'Prohibited')"
        ).fetchone()[0]

    size_kb = round(db_path.stat().st_size / 1024, 1)

    return {
        "initialized": True,
        "products_count": products_count,
        "ingredients_count": ingredients_count,
        "standards_count": standards_count,
        "history_count": history_count,
        "allergens_count": allergens_count,
        "banned_records": banned_count,
        "db_size_kb": size_kb,
        "db_path": str(db_path),
    }
