use std::io::Write;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use tempfile::NamedTempFile;

use clickgraph_embedded::{Connection, Database, SqlDialect};

/// Compiles an openCypher query + YAML schema string into ClickHouse SQL in memory.
#[pyfunction]
#[pyo3(signature = (yaml_schema, cypher_query, dialect = "clickhouse"))]
fn compile_to_sql(yaml_schema: &str, cypher_query: &str, dialect: &str) -> PyResult<String> {
    let mut tmp = NamedTempFile::new()
        .map_err(|e| PyValueError::new_err(format!("Temp file error: {e}")))?;
    tmp.write_all(yaml_schema.as_bytes())
        .map_err(|e| PyValueError::new_err(format!("YAML write error: {e}")))?;

    let sql_dialect = match dialect.to_lowercase().as_str() {
        "databricks" | "spark" => SqlDialect::Databricks,
        _ => SqlDialect::ClickHouse,
    };

    let db = Database::sql_only_with_dialect(tmp.path(), sql_dialect)
        .map_err(|e| PyValueError::new_err(format!("Schema parse error: {e}")))?;

    let conn = Connection::new(&db)
        .map_err(|e| PyValueError::new_err(format!("Connection init error: {e}")))?;

    let sql = conn
        .query_to_sql(cypher_query)
        .map_err(|e| PyValueError::new_err(format!("Cypher compile error: {e}")))?;

    Ok(sql)
}

/// Validates a YAML schema from the RedLens UI without running a query.
#[pyfunction]
fn validate_schema(yaml_schema: &str) -> PyResult<bool> {
    let mut tmp = NamedTempFile::new()
        .map_err(|e| PyValueError::new_err(format!("Temp file error: {e}")))?;
    tmp.write_all(yaml_schema.as_bytes())
        .map_err(|e| PyValueError::new_err(format!("YAML write error: {e}")))?;

    Database::sql_only(tmp.path())
        .map_err(|e| PyValueError::new_err(format!("Invalid graph schema: {e}")))?;
    Ok(true)
}

/// Registers the compiled Rust extension module as `cyphersql._core`.
#[pymodule]
#[pyo3(name = "_core")]
fn core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compile_to_sql, m)?)?;
    m.add_function(wrap_pyfunction!(validate_schema, m)?)?;
    Ok(())
}