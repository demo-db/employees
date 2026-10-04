#!/usr/bin/env python3
"""Build the fixed Employees browser edition from hash-pinned upstream SQL dumps."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
OUTPUT = ROOT / "data-source" / "source.sqlite.gz"
TABLE_COLUMNS = {
    "departments": ("dept_no", "dept_name"),
    "employees": ("emp_no", "birth_date", "first_name", "last_name", "gender", "hire_date"),
    "dept_manager": ("emp_no", "dept_no", "from_date", "to_date"),
    "dept_emp": ("emp_no", "dept_no", "from_date", "to_date"),
    "titles": ("emp_no", "title", "from_date", "to_date"),
    "salaries": ("emp_no", "salary", "from_date", "to_date"),
}
SOURCE_FILES = {
    "departments": ("load_departments.dump", "departments"),
    "employees": ("load_employees.dump", "employees"),
    "dept_manager": ("load_dept_manager.dump", "dept_manager"),
    "dept_emp": ("load_dept_emp.dump", "dept_emp"),
    "titles": ("load_titles.dump", "titles"),
    # Salary history is split into three upstream dump files; all are required
    # inputs and are parsed in order below.
    "salaries": ("load_salaries1.dump", "salaries"),
}
SALARY_FILES = tuple(f"load_salaries{index}.dump" for index in (1, 2, 3))


class BuildError(RuntimeError):
    pass


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def manifest() -> dict[str, Any]:
    result = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if result.get("source", {}).get("revision") != "e324b56193ca506ab7cc1ab143a9153d8c4535d7":
        raise BuildError("manifest source revision differs from the reviewed upstream pin")
    return result


def verify_inputs(source_dir: Path, manifest_data: dict[str, Any]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    pinned = {Path(item["path"]).name: item["sha256"] for item in manifest_data["source"]["recipe"]}
    required = {Path(item[0]).name for item in SOURCE_FILES.values()} | set(SALARY_FILES) | {"employees.sql"}
    if required != set(pinned):
        raise BuildError(f"manifest source recipe must pin exactly these files: {sorted(required)}")
    for name, expected in pinned.items():
        path = source_dir / name
        if not path.is_file():
            raise BuildError(f"pinned source file is missing: {path}")
        actual = sha256(path.read_bytes())
        if actual != expected:
            raise BuildError(f"upstream source SHA-256 mismatch for {name}: expected {expected}, got {actual}")
        paths[name] = path
    return paths


def parse_literal(text: str, position: int) -> tuple[Any, int]:
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text):
        raise BuildError("unexpected end of input in a SQL INSERT value")
    if text[position] == "'":
        position += 1
        value: list[str] = []
        escapes = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a", "\\": "\\", "'": "'", '"': '"', "%": "%", "_": "_"}
        while position < len(text):
            char = text[position]
            if char == "\\":
                position += 1
                if position >= len(text):
                    raise BuildError("unterminated MySQL escape in a SQL string")
                escaped = text[position]
                value.append(escapes.get(escaped, escaped))
                position += 1
            elif char == "'":
                if position + 1 < len(text) and text[position + 1] == "'":
                    value.append("'")
                    position += 2
                else:
                    return "".join(value), position + 1
            else:
                value.append(char)
                position += 1
        raise BuildError("unterminated SQL string literal")
    end = position
    while end < len(text) and text[end] not in ",);" and not text[end].isspace():
        end += 1
    token = text[position:end]
    if token.upper() == "NULL":
        return None, end
    if re.fullmatch(r"[-+]?\d+", token):
        return int(token), end
    raise BuildError(f"unsupported SQL INSERT literal: {token!r}")


def parse_insert_dump(path: Path, expected_table: str, expected_columns: int) -> Iterator[tuple[Any, ...]]:
    text = path.read_text(encoding="utf-8", errors="strict")
    pattern = re.compile(r"INSERT\s+INTO\s+`?([A-Za-z_][A-Za-z0-9_]*)`?\s+VALUES\s*", re.I)
    position = 0
    rows = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        match = pattern.match(text, position)
        if not match or match.group(1).lower() != expected_table.lower():
            raise BuildError(f"{path.name} contains unexpected SQL at offset {position}")
        position = match.end()
        while True:
            while position < len(text) and text[position].isspace():
                position += 1
            if position >= len(text) or text[position] != "(":
                raise BuildError(f"expected tuple at byte-like offset {position} in {path.name}")
            position += 1
            values: list[Any] = []
            while True:
                value, position = parse_literal(text, position)
                values.append(value)
                while position < len(text) and text[position].isspace():
                    position += 1
                if position >= len(text):
                    raise BuildError(f"unterminated tuple in {path.name}")
                if text[position] == ",":
                    position += 1
                    continue
                if text[position] == ")":
                    position += 1
                    break
                raise BuildError(f"expected comma or closing parenthesis in {path.name}")
            if len(values) != expected_columns:
                raise BuildError(f"{path.name} row has {len(values)} values; expected {expected_columns}")
            rows += 1
            yield tuple(values)
            while position < len(text) and text[position].isspace():
                position += 1
            if position < len(text) and text[position] == ",":
                position += 1
                while position < len(text) and text[position].isspace():
                    position += 1
                if position >= len(text) or text[position] != "(":
                    raise BuildError(f"expected tuple after comma in {path.name}")
                continue
            if position >= len(text) or text[position] != ";":
                raise BuildError(f"expected tuple separator in {path.name}")
            position += 1
            break
    if not rows:
        raise BuildError(f"no {expected_table} rows found in {path.name}")


def load_upstream_rows(source_paths: dict[str, Path], expected_counts: dict[str, int]) -> tuple[dict[str, list[tuple[Any, ...]]], dict[str, int]]:
    departments = list(parse_insert_dump(source_paths["load_departments.dump"], "departments", 2))
    managers = list(parse_insert_dump(source_paths["load_dept_manager.dump"], "dept_manager", 4))
    department_names = {str(row[0]) for row in departments}
    manager_ids = {int(row[0]) for row in managers}
    if len(managers) != 24 or len(manager_ids) != 24:
        raise BuildError(f"expected 24 unique manager employee IDs, got {len(manager_ids)}")
    if len(departments) != 9:
        raise BuildError(f"expected all 9 source departments, got {len(departments)}")
    selected_ids = set(range(10001, 11001)) | manager_ids
    if len(selected_ids) != 1024:
        raise BuildError(f"expected exactly 1,024 selected employees, got {len(selected_ids)}")
    retained: dict[str, list[tuple[Any, ...]]] = {
        "departments": departments,
        "employees": [],
        "dept_manager": managers,
        "dept_emp": [],
        "titles": [],
        "salaries": [],
    }
    source_counts = {"departments": len(departments), "dept_manager": len(managers)}
    for table, (filename, _) in SOURCE_FILES.items():
        if table in source_counts:
            continue
        path = source_paths[filename]
        count = 0
        if table == "salaries":
            salary_files = [source_paths[name] for name in SALARY_FILES]
            for salary_path in salary_files:
                for row in parse_insert_dump(salary_path, "salaries", 4):
                    count += 1
                    if int(row[0]) in selected_ids:
                        retained[table].append(row)
        else:
            for row in parse_insert_dump(path, table, len(TABLE_COLUMNS[table])):
                count += 1
                if table == "employees":
                    if int(row[0]) in selected_ids:
                        retained[table].append(row)
                elif int(row[0]) in selected_ids:
                    retained[table].append(row)
        source_counts[table] = count
    source_counts["salaries"] = source_counts.pop("salaries", 0)
    if source_counts != expected_counts:
        raise BuildError(f"upstream row counts differ from the pinned source: {source_counts}")
    if len(retained["employees"]) != 1024:
        raise BuildError(f"selected employee set is not FK-closed: retained {len(retained['employees'])} employee rows")
    if {int(row[0]) for row in retained["employees"]} != selected_ids:
        raise BuildError("selected employee source rows do not exactly equal the declared ID set")
    for table in ("dept_emp", "dept_manager"):
        if any(str(row[1]) not in department_names for row in retained[table]):
            raise BuildError(f"{table} references a department outside the selected nine")
    retained_ids = {int(row[0]) for row in retained["employees"]}
    for table in ("dept_emp", "dept_manager", "titles", "salaries"):
        if any(int(row[0]) not in retained_ids for row in retained[table]):
            raise BuildError(f"{table} references an employee outside the selected set")
    return retained, source_counts


def build_database(path: Path, rows: dict[str, list[tuple[Any, ...]]]) -> dict[str, int]:
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.executescript(
            """
            CREATE TABLE departments (
                dept_no TEXT NOT NULL PRIMARY KEY,
                dept_name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE employees (
                emp_no INTEGER NOT NULL PRIMARY KEY,
                birth_date TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                gender TEXT NOT NULL CHECK (gender IN ('M', 'F')),
                hire_date TEXT NOT NULL
            );
            CREATE TABLE dept_emp (
                emp_no INTEGER NOT NULL,
                dept_no TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                PRIMARY KEY (emp_no, dept_no),
                FOREIGN KEY (emp_no) REFERENCES employees(emp_no) ON DELETE CASCADE,
                FOREIGN KEY (dept_no) REFERENCES departments(dept_no) ON DELETE CASCADE
            );
            CREATE TABLE dept_manager (
                emp_no INTEGER NOT NULL,
                dept_no TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                PRIMARY KEY (emp_no, dept_no),
                FOREIGN KEY (emp_no) REFERENCES employees(emp_no) ON DELETE CASCADE,
                FOREIGN KEY (dept_no) REFERENCES departments(dept_no) ON DELETE CASCADE
            );
            CREATE TABLE titles (
                emp_no INTEGER NOT NULL,
                title TEXT NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT,
                PRIMARY KEY (emp_no, title, from_date),
                FOREIGN KEY (emp_no) REFERENCES employees(emp_no) ON DELETE CASCADE
            );
            CREATE TABLE salaries (
                emp_no INTEGER NOT NULL,
                salary INTEGER NOT NULL,
                from_date TEXT NOT NULL,
                to_date TEXT NOT NULL,
                PRIMARY KEY (emp_no, from_date),
                FOREIGN KEY (emp_no) REFERENCES employees(emp_no) ON DELETE CASCADE
            );
            """
        )
        for table in ("departments", "employees", "dept_emp", "dept_manager", "titles", "salaries"):
            columns = TABLE_COLUMNS[table]
            placeholders = ",".join("?" for _ in columns)
            db.executemany(f"INSERT INTO \"{table}\" VALUES ({placeholders})", rows[table])
        db.executescript(
            """
            CREATE VIEW dept_emp_latest_date AS
              SELECT emp_no, MAX(from_date) AS from_date, MAX(to_date) AS to_date
              FROM dept_emp GROUP BY emp_no;
            CREATE VIEW current_dept_emp AS
              SELECT l.emp_no, d.dept_no, l.from_date, l.to_date
              FROM dept_emp AS d
              INNER JOIN dept_emp_latest_date AS l
                ON d.emp_no = l.emp_no AND d.from_date = l.from_date AND l.to_date = d.to_date;
            """
        )
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BuildError("SQLite integrity_check failed")
        fk_errors = db.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise BuildError(f"SQLite foreign_key_check found {len(fk_errors)} violations")
        counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in TABLE_COLUMNS}
        if len({row[0] for row in db.execute("SELECT emp_no FROM employees")}) != 1024:
            raise BuildError("employee primary key count differs from selected employee count")
        return counts
    finally:
        db.close()


def logical_snapshot(path: Path) -> bytes:
    db = sqlite3.connect(path)
    try:
        schema = [tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        contents = []
        for kind, name in db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type,name"):
            columns = [row[1] for row in db.execute(f'PRAGMA table_xinfo("{name}")')] if kind == "table" else [x[0] for x in (db.execute(f'SELECT * FROM "{name}" LIMIT 0').description or [])]
            order = ",".join(f'"{column}"' for column in columns)
            rows = [tuple(row) for row in db.execute(f'SELECT * FROM "{name}" ORDER BY {order}')]
            contents.append((name, rows))
        return json.dumps({"schema": schema, "contents": contents}, sort_keys=True, ensure_ascii=False).encode()
    finally:
        db.close()


def make_gzip(data: bytes) -> bytes:
    import io

    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=9) as stream:
        stream.write(data)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True, help="directory containing files downloaded by fetch-source.py")
    parser.add_argument("--check", action="store_true", help="rebuild in temporary storage and compare full logical database contents")
    args = parser.parse_args()
    config = manifest()
    source_paths = verify_inputs(args.source_dir.resolve(), config)
    retained, source_counts = load_upstream_rows(source_paths, config["source"]["fullTableCounts"])
    with tempfile.TemporaryDirectory(prefix="employees-rebuild-") as temporary:
        candidate = Path(temporary) / "source.sqlite"
        counts = build_database(candidate, retained)
        candidate_bytes = candidate.read_bytes()
        candidate_snapshot = logical_snapshot(candidate)
    expected_counts = config.get("subset", {}).get("rowCounts")
    if args.check:
        if not OUTPUT.is_file():
            raise BuildError(f"compressed SQLite fixture is missing: {OUTPUT}")
        compressed = OUTPUT.read_bytes()
        expected_input_sha = config["source"].get("inputSha256")
        if sha256(compressed) != expected_input_sha:
            raise BuildError("compressed SQLite hash differs from manifest source.inputSha256")
        decoded = gzip.decompress(compressed)
        if sha256(decoded) != config["source"].get("databaseSha256"):
            raise BuildError("decompressed SQLite hash differs from manifest source.databaseSha256")
        with tempfile.TemporaryDirectory(prefix="employees-fixture-check-") as temporary:
            fixture = Path(temporary) / "source.sqlite"
            fixture.write_bytes(decoded)
            if candidate_snapshot != logical_snapshot(fixture):
                raise BuildError("rebuilt database differs from the committed SQLite schema or rows")
        if expected_counts != counts:
            raise BuildError(f"selected row counts differ from manifest: expected {expected_counts}, got {counts}")
        print(f"Employees source check passed: {counts}; full pinned source rows: {source_counts}")
        return 0
    if expected_counts is not None and expected_counts != counts:
        raise BuildError(f"selected row counts differ from manifest: expected {expected_counts}, got {counts}")
    compressed = make_gzip(candidate_bytes)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(compressed)
    digest = sha256(candidate_bytes)
    input_digest = sha256(compressed)
    print(f"Built Employees browser edition: {counts}; SQLite SHA-256 {digest}; gzip SHA-256 {input_digest}")
    if config["source"].get("databaseSha256") != digest or config["source"].get("inputSha256") != input_digest:
        raise BuildError("update manifest source databaseSha256/inputSha256 from this deterministic build")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, sqlite3.Error, BuildError) as error:
        raise SystemExit(f"error: {error}")
