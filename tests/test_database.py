"""
tests/test_database.py - 数据库模块单元测试
"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pathlib import Path
from unittest.mock import patch
import database as db_module
from database import (
    init_database, upsert_product, save_product_ingredients,
    get_product_with_ingredients, get_ingredient_details,
    search_ingredients, get_banned_ingredients,
    save_query_history_db, get_query_history_db, get_db_stats,
    get_connection,
)


@pytest.fixture
def tmp_db(tmp_path):
    """每个测试使用独立的临时数据库"""
    db_path = tmp_path / "test.db"
    # Patch 数据目录以便导入 JSON
    with patch.object(db_module, "DB_PATH", db_path), \
         patch.object(db_module, "INGREDIENTS_JSON",
                      Path(__file__).parent.parent / "data" / "ingredients_db.json"):
        init_database(db_path)
        yield db_path


class TestInitDatabase:
    def test_tables_created(self, tmp_db):
        with get_connection(tmp_db) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        expected = {"products", "ingredients", "product_ingredients",
                    "safety_standards", "query_history"}
        assert expected.issubset(tables)

    def test_ingredients_imported(self, tmp_db):
        stats = get_db_stats(tmp_db)
        assert stats["ingredients_count"] > 10, "应从 JSON 导入至少10种成分"

    def test_safety_standards_imported(self, tmp_db):
        stats = get_db_stats(tmp_db)
        assert stats["standards_count"] > 0, "应导入安全标准数据"


class TestProductOperations:
    def test_upsert_product_new(self, tmp_db):
        pid = upsert_product("TestBrand", "TestProduct", db_path=tmp_db)
        assert isinstance(pid, int)
        assert pid > 0

    def test_upsert_product_idempotent(self, tmp_db):
        pid1 = upsert_product("Brand", "ProductA", db_path=tmp_db)
        pid2 = upsert_product("Brand", "ProductA", db_path=tmp_db)
        assert pid1 == pid2

    def test_upsert_different_products(self, tmp_db):
        pid1 = upsert_product("Brand", "ProductA", db_path=tmp_db)
        pid2 = upsert_product("Brand", "ProductB", db_path=tmp_db)
        assert pid1 != pid2

    def test_save_and_retrieve_product_ingredients(self, tmp_db):
        pid = upsert_product("Olay", "Moisturizer", db_path=tmp_db)
        ingredients = ["Water", "Glycerin", "Niacinamide"]
        save_product_ingredients(pid, ingredients, db_path=tmp_db)

        result = get_product_with_ingredients("Olay", "Moisturizer", db_path=tmp_db)
        assert result is not None
        assert result["brand"] == "Olay"
        assert len(result["ingredients"]) == 3
        ing_names = [i["inci_name"] for i in result["ingredients"]]
        assert "Niacinamide" in ing_names

    def test_product_ingredients_position_order(self, tmp_db):
        pid = upsert_product("Brand", "OrderTest", db_path=tmp_db)
        ingredients = ["Water", "Glycerin", "Niacinamide", "Phenoxyethanol"]
        save_product_ingredients(pid, ingredients, db_path=tmp_db)

        result = get_product_with_ingredients("Brand", "OrderTest", db_path=tmp_db)
        positions = [i["position"] for i in result["ingredients"]]
        assert positions == sorted(positions)

    def test_get_nonexistent_product(self, tmp_db):
        result = get_product_with_ingredients("NoSuch", "Product", db_path=tmp_db)
        assert result is None

    def test_unknown_ingredient_auto_inserted(self, tmp_db):
        pid = upsert_product("Brand", "NewProduct", db_path=tmp_db)
        ingredients = ["Water", "SomeUnknownIngredient99999"]
        save_product_ingredients(pid, ingredients, db_path=tmp_db)

        result = get_product_with_ingredients("Brand", "NewProduct", db_path=tmp_db)
        ing_names = [i["inci_name"] for i in result["ingredients"]]
        assert "SomeUnknownIngredient99999" in ing_names


class TestIngredientSearch:
    def test_search_by_inci(self, tmp_db):
        results = search_ingredients("Water", limit=5, db_path=tmp_db)
        assert len(results) >= 1
        assert any("water" in r["inci_name"].lower() for r in results)

    def test_search_case_insensitive(self, tmp_db):
        r1 = search_ingredients("glycerin", limit=5, db_path=tmp_db)
        r2 = search_ingredients("GLYCERIN", limit=5, db_path=tmp_db)
        assert len(r1) == len(r2)

    def test_search_partial_match(self, tmp_db):
        results = search_ingredients("Niacin", limit=5, db_path=tmp_db)
        assert len(results) >= 1

    def test_search_no_result(self, tmp_db):
        results = search_ingredients("XYZ_NONEXISTENT_99999", db_path=tmp_db)
        assert results == []

    def test_get_ingredient_details(self, tmp_db):
        details = get_ingredient_details("Water", db_path=tmp_db)
        assert details is not None
        assert details["inci_name"] == "Water"
        assert details["safety_score"] == 10
        assert "FDA" in details["standards"]

    def test_get_banned_ingredients_fda(self, tmp_db):
        banned = get_banned_ingredients("FDA", db_path=tmp_db)
        assert isinstance(banned, list)
        # 应该包含 Triclosan, Mercury 等
        inci_names = [b["inci_name"].lower() for b in banned]
        assert any("triclosan" in n or "mercury" in n or "lead" in n for n in inci_names)


class TestQueryHistory:
    def test_save_and_retrieve(self, tmp_db):
        save_query_history_db(
            "TestBrand", "TestProduct", None,
            "web_scraper", {"score": 8.0},
            db_path=tmp_db
        )
        history = get_query_history_db(limit=10, db_path=tmp_db)
        assert len(history) >= 1
        assert history[0]["brand"] == "TestBrand"

    def test_history_limit(self, tmp_db):
        for i in range(15):
            save_query_history_db(
                f"Brand{i}", f"Product{i}", None, "test", {},
                db_path=tmp_db
            )
        history = get_query_history_db(limit=5, db_path=tmp_db)
        assert len(history) == 5

    def test_history_latest_first(self, tmp_db):
        save_query_history_db("BrandA", "ProductA", None, "test", {}, db_path=tmp_db)
        save_query_history_db("BrandB", "ProductB", None, "test", {}, db_path=tmp_db)
        history = get_query_history_db(limit=10, db_path=tmp_db)
        assert history[0]["brand"] == "BrandB"


class TestDbStats:
    def test_stats_structure(self, tmp_db):
        stats = get_db_stats(tmp_db)
        required_keys = [
            "initialized", "products_count", "ingredients_count",
            "standards_count", "history_count", "allergens_count",
            "banned_records", "db_size_kb"
        ]
        for k in required_keys:
            assert k in stats

    def test_allergens_counted(self, tmp_db):
        stats = get_db_stats(tmp_db)
        assert stats["allergens_count"] > 0, "应有已知致敏原"
