import pytest
from cyphersql import GraphCompiler, compile_cypher

SCHEMA = {
    "name": "vfcash_scope",
    "graph_schema": {
        "nodes": [
            {
                "label": "Wallet",
                "database": "vfcash",
                "table": "wallets",
                "node_id": "msisdn",
                "property_mappings": {
                    "msisdn": "msisdn",
                    "owner_name": "owner_name",
                    "risk_tier": "risk_tier",
                },
            }
        ],
        "edges": [
            {
                "type": "TRANSFERRED_TO",
                "database": "vfcash",
                "table": "transfers",
                "from_node": "Wallet",
                "to_node": "Wallet",
                "from_id": "sender",
                "to_id": "receiver",
                "property_mappings": {
                    "amount": "amount",
                    "tx_ts": "tx_ts",
                },
            }
        ],
    },
}


@pytest.fixture
def compiler():
    return GraphCompiler(SCHEMA)


def test_fixed_hop_with_where_filter(compiler):
    cypher = """
    MATCH (a:Wallet)-[r:TRANSFERRED_TO]->(b:Wallet)
    WHERE a.msisdn = '01001111111' AND r.amount > 5000
    RETURN a.owner_name, b.owner_name, r.amount
    LIMIT 20
    """
    ch_sql = compiler.compile(cypher, dialect="clickhouse")
    trino_sql = compiler.compile(cypher, dialect="trino")
    assert "vfcash.transfers" in ch_sql
    assert "5000" in trino_sql
    assert "SETTINGS" not in trino_sql


def test_variable_length_path_multi_dialect(compiler):
    cypher = "MATCH p = (a:Wallet)-[:TRANSFERRED_TO*1..3]->(b:Wallet) RETURN a.owner_name, b.owner_name, length(p)"
    
    ch_sql = compiler.compile(cypher, dialect="clickhouse")
    assert "WITH RECURSIVE" in ch_sql
    assert "has(vp.path_edges" in ch_sql

    trino_sql = compiler.compile(cypher, dialect="trino")
    assert "WITH RECURSIVE vlp_v1_path(" in trino_sql
    assert "CONTAINS(vp.path_edges, ROW(" in trino_sql

    pg_sql = compiler.compile(cypher, dialect="postgres")
    assert "WITH RECURSIVE" in pg_sql


def test_shortest_path(compiler):
    cypher = """
    MATCH p = shortestPath((a:Wallet {msisdn: '01001111111'})-[:TRANSFERRED_TO*1..4]->(b:Wallet {msisdn: '01009999999'}))
    RETURN a.owner_name, b.owner_name, length(p)
    """
    sql = compiler.compile(cypher, dialect="clickhouse")
    assert "WITH RECURSIVE" in sql
    assert "LIMIT 1" in sql or "hop_count" in sql


def test_aggregation_and_grouping(compiler):
    cypher = """
    MATCH (a:Wallet)-[r:TRANSFERRED_TO]->(b:Wallet)
    RETURN a.msisdn, count(b) AS tx_count, sum(r.amount) AS total_sent
    ORDER BY total_sent DESC
    LIMIT 10
    """
    trino_sql = compiler.compile(cypher, dialect="trino")
    assert "COUNT(" in trino_sql.upper()
    assert "SUM(" in trino_sql.upper()
    assert "GROUP BY" in trino_sql.upper()


def test_parameter_placeholder_and_binding(compiler):
    cypher = "MATCH (a:Wallet {msisdn: $target_msisdn})-[:TRANSFERRED_TO]->(b:Wallet) RETURN b.msisdn"
    
    # Unbound placeholder preserved as @target_msisdn
    unbound_sql = compiler.compile(cypher, dialect="clickhouse")
    assert "@target_msisdn" in unbound_sql

    # Bound parameter safely escaped in AST for Trino & ClickHouse
    bound_trino = compiler.compile(cypher, dialect="trino", params={"target_msisdn": "01001111111"})
    assert "'01001111111'" in bound_trino
    assert "@target_msisdn" not in bound_trino


def test_invalid_schema_raises():
    with pytest.raises(ValueError):
        GraphCompiler("invalid: yaml: content")
