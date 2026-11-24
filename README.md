# cyphersql

**In-process, zero-ETL openCypher-to-SQL compiler for Python**, powered by a compiled Rust core (`PyO3` + `abi3`) and `sqlglot`.

`cyphersql` compiles openCypher graph queries—including variable-length traversals (`*1..N`), `shortestPath()`, aggregations, and bound parameters—directly into native SQL for **ClickHouse**, **Trino / Apache Iceberg**, **PostgreSQL**, **MySQL**, **DuckDB**, and **Databricks** in ~1ms with **zero HTTP sidecar processes** and **zero data movement**.

---

## Why `cyphersql`?

Traditional graph overlays either force you to ETL your warehouse tables into a separate graph database or deploy a heavy JVM/HTTP sidecar service just to translate Cypher into SQL. `cyphersql` eliminates both:

- **In-Process Rust Execution (`abi3`):** Compiled as a single cross-version Python wheel (`Python >= 3.10`)—import it directly into FastAPI, Airflow, or Python scripts with ~1ms compilation latency.
- **Multi-Engine Dialect Output:** Compiles openCypher into relational plans in Rust and transpiles them via `sqlglot` AST rewrites into dialect-accurate SQL (automatically converting ClickHouse recursive CTE helpers such as `has()` into Trino `CONTAINS()` and stripping engine-specific `SETTINGS`).
- **Zero-ETL Semantic Mapping:** Maps logical graph nodes and relationships directly onto existing analytical tables (`database.table`) using YAML or Python dictionaries.
- **Safe Parameter Binding:** Supports both unbound placeholders (`@param`) and AST-escaped literal binding (`params={...}`).

---

## Installation

```bash
pip install cyphersql

```

---

## Quick Start

### 1. Define Your Graph Mapping & Compile Queries

`GraphCompiler` accepts either a Python dictionary (such as a JSON payload from a visual schema builder) or a raw YAML string.

```python
from cyphersql import GraphCompiler, compile_cypher

schema = {
    "name": "payments_graph",
    "graph_schema": {
        "nodes": [
            {
                "label": "Wallet",
                "database": "analytics",
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
                "database": "analytics",
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

compiler = GraphCompiler(schema)

cypher = """
MATCH p = (a:Wallet {msisdn: $sender})-[:TRANSFERRED_TO*1..3]->(b:Wallet)
RETURN a.owner_name AS sender, b.owner_name AS receiver, length(p) AS hops
"""

# 1. Native ClickHouse SQL
ch_sql = compiler.compile(
    cypher,
    dialect="clickhouse",
    params={"sender": "01001111111"},
    pretty=True,
)

# 2. Trino / Apache Iceberg SQL (compatible with Apache Ranger policies)
trino_sql = compiler.compile(
    cypher,
    dialect="trino",
    params={"sender": "01001111111"},
    pretty=True,
)

# 3. PostgreSQL / MySQL / DuckDB SQL
pg_sql = compiler.compile(
    cypher,
    dialect="postgres",
    params={"sender": "01001111111"},
    pretty=True,
)

```

### 2. One-Line Compilation

```python
sql = compile_cypher(
    schema,
    "MATCH (a:Wallet)-[r:TRANSFERRED_TO]->(b:Wallet) WHERE r.amount > 5000 RETURN a.msisdn, b.msisdn, r.amount LIMIT 20",
    dialect="trino",
    pretty=True,
)

```

---

## Supported Dialects & Cypher Constructs

| Target Dialect | `dialect=` Argument | Recursive VLP (`*1..N`) | Cycle Prevention | Parameter Binding |
| --- | --- | --- | --- | --- |
| **ClickHouse** | `"clickhouse"` | `WITH RECURSIVE` | `NOT has(path_edges, tuple(...))` | `@param` / bound literals |
| **Trino / Iceberg** | `"trino"` | `WITH RECURSIVE cte(...)` | `NOT CONTAINS(path_edges, ROW(...))` | `@param` / bound literals |
| **PostgreSQL** | `"postgres"` | `WITH RECURSIVE` | `sqlglot` AST rewrite | `@param` / bound literals |
| **MySQL** | `"mysql"` | `WITH RECURSIVE` | `sqlglot` AST rewrite | `@param` / bound literals |
| **DuckDB** | `"duckdb"` | `WITH RECURSIVE` | `sqlglot` AST rewrite | `@param` / bound literals |
| **Databricks** | `"databricks"` | Native Databricks emitter | Native emitter | `@param` / bound literals |

---

## API Reference

### `GraphCompiler(schema: str | dict)`

Validates the YAML or dictionary graph schema upon initialization and caches it for fast repeated compilation.

* `compiler.compile(cypher: str, dialect: str = "clickhouse", pretty: bool = False, params: dict | None = None) -> str`
Compiles an openCypher query into SQL for the target dialect. Raises `ValueError` on invalid Cypher syntax or unmapped node/edge labels.

### `compile_cypher(schema: str | dict, cypher: str, dialect: str = "clickhouse", pretty: bool = False, params: dict | None = None) -> str`

Stateless helper function that validates `schema` and compiles `cypher` in a single call.

---

## Architecture

```text
openCypher Query + YAML/Dict Schema
                │
                ▼
┌─────────────────────────────────────────┐
│  cyphersql._core (Rust / PyO3 abi3)     │
│  • YAML Schema Validator                │
│  • openCypher AST Parser                │
│  • Relational & Recursive CTE Planner   │
└───────────────┬─────────────────────────┘
                │ Raw ClickHouse / Databricks SQL
                ▼
┌─────────────────────────────────────────┐
│  cyphersql.compiler (Python / sqlglot)  │
│  • $param -> AST Parameter Binding      │
│  • ClickHouse -> Trino/PG/MySQL Rewrite │
└───────────────┬─────────────────────────┘
                │
                ▼
   Native SQL Ready for Execution

```

---

## Building from Source

Requires Rust (`rustc >= 1.85`) and Python (`>= 3.10`).

```bash
git clone [https://github.com/MahmoudHassanen99/cyphersql.git](https://github.com/MahmoudHassanen99/cyphersql.git)
cd cyphersql

python -m venv .venv
source .venv/bin/activate
pip install maturin sqlglot pyyaml pytest

# Compile Rust extension in release mode and install editable package
maturin develop --release

# Run test suite
pytest -v

```

---

## License & Attribution

Licensed under the **Apache License 2.0**. See [`LICENSE`](https://www.google.com/search?q=LICENSE) for full terms.

The underlying Rust openCypher-to-SQL planner embeds components from [ClickGraph](https://github.com/genezhang/clickgraph) (Apache-2.0); original copyright and license notices are preserved in `LICENSE` and `vendor/clickgraph/LICENSE`.
