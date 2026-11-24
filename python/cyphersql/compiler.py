import re
import yaml
import sqlglot
from sqlglot import exp
from cyphersql._core import compile_to_sql, validate_schema

_CYPHER_PARAM_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


class GraphCompiler:
    def __init__(self, schema: str | dict):
        """Accepts either a raw YAML string or a Python dict (from your UI JSON)."""
        if isinstance(schema, dict):
            self.yaml_str = yaml.safe_dump(schema, sort_keys=False)
        else:
            self.yaml_str = schema
        validate_schema(self.yaml_str)

    def compile(
        self,
        cypher: str,
        dialect: str = "clickhouse",
        pretty: bool = False,
        params: dict | None = None,
    ) -> str:
        """
        Compiles openCypher into native SQL for the requested target dialect.
        Supported dialects: 'clickhouse', 'trino', 'postgres', 'mysql', 'duckdb', 'databricks'
        """
        target = dialect.lower()
        rust_dialect = "databricks" if target in ("databricks", "spark") else "clickhouse"

        # 1. Compile openCypher -> ClickHouse/Databricks SQL in RAM via Rust FFI
        raw_sql = compile_to_sql(self.yaml_str, cypher, rust_dialect)

        # 2. Convert Cypher `$param` -> sqlglot `@param` placeholder so ClickHouse dollar-quoting doesn't collide
        normalized_sql = _CYPHER_PARAM_RE.sub(r"@\1", raw_sql)

        if target in ("clickhouse", "databricks", "spark"):
            ast = sqlglot.parse_one(normalized_sql, read=rust_dialect)
        else:
            ast = sqlglot.parse_one(normalized_sql, read="clickhouse")
            ast = self._normalize_ast(ast)

        # 3. Substitute bound parameter values via sqlglot AST if `params` dict is provided
        if params:
            ast = self._bind_params(ast, params)

        return ast.sql(dialect=target, pretty=pretty)

    @staticmethod
    def _normalize_ast(ast: exp.Expression) -> exp.Expression:
        def transform(node):
            # Map ClickHouse `has(array, elem)` -> portable ArrayContains (`CONTAINS` in Trino, `ANY` in Postgres)
            if isinstance(node, exp.Anonymous) and node.name.lower() == "has":
                args = node.expressions
                if len(args) == 2:
                    return exp.ArrayContains(this=args[0], expression=args[1])
            return node

        return ast.transform(transform)

    @staticmethod
    def _bind_params(ast: exp.Expression, params: dict) -> exp.Expression:
        def replace_param(node):
            if isinstance(node, exp.Parameter):
                name = node.name
                if name in params:
                    return exp.convert(params[name])
            return node

        return ast.transform(replace_param)


def compile_cypher(
    schema: str | dict,
    cypher: str,
    dialect: str = "clickhouse",
    pretty: bool = False,
    params: dict | None = None,
) -> str:
    """One-line functional entrypoint."""
    return GraphCompiler(schema).compile(cypher, dialect=dialect, pretty=pretty, params=params)
