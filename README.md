# Employees (browser edition)

A reproducible, browser-sized edition of the MySQL Employees sample database. This is a selected subset, not the complete upstream dataset. It contains 1,024 employees: IDs 10001–11000 plus every distinct manager ID in the source sample, all nine departments, all 24 manager assignments, and every department, title, and salary history row for the selected people. It retains the six native tables and both native views.

The upstream project says the sample data is fabricated and does not correspond to real people. Its `employees.sql` header credits MySQL AB (2007/2008), original data creators Fusheng Wang and Carlo Zaniolo, schema author Giuseppe Maxia, and XML conversion by Patrick Crews. The header licenses the work under CC BY-SA 3.0 Unported. This selected, adapted database and its derived model metadata are distributed under the same share-alike license; see [`LICENSE`](LICENSE).

The pinned upstream source and reproducible selection are documented in [`data-source/README.md`](data-source/README.md). Run `python3 scripts/fetch-source.py --destination /tmp/employees-source` to download and hash-check every required upstream file, then `python3 scripts/rebuild-source.py --source-dir /tmp/employees-source --check` to verify the checked-in compressed SQLite fixture. The converter preserves native table and view names, primary/unique keys and foreign keys, ISO dates, integer salary values, and exact text values. It does not invent rows or currency information.

The verified read-only OVDB mount provides record lookups and query access; writes remain disabled.

## Native inGitDB snapshot

The `ingitdb/` directory contains 13,584 source rows in 6 collections, exported from the pinned SQLite fixture by DataTug's generic DALgo → inGitDB exporter. The source fixture SHA-256 is `46b49dd0e141cd8db66d57680a10febfccc15e6f54dc7b8f3c2316b55e11c5f0`. This Git-backed edition is a queryable snapshot, not a live SQL database.

Use DataTug CLI v0.61.1 or newer to reproduce this export, and inGitDB CLI v0.70.0 or newer to validate and query this edition.

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from 'departments' --limit 1 --format json
```

Each source table has a `.collection/definition.yaml` with ordered fields, source primary-key columns, portable indexes and foreign-key groups/actions. `.ingitdb/source-collections.json` maps native collection IDs to exact SQLite table names; names outside inGitDB’s ID alphabet use a deterministic `dt_` UTF-8 hex ID. Its `source_schema.source_definition_json` retains the original SQLite DDL, declared column types, defaults and complete index details. The native record file is `records.json`, keyed by deterministic transport IDs derived from the ordered source primary key; keyless tables use source-row ordinals. These transport IDs are not new SQL columns. Exact decimals are stored as strings, BLOBs as base64, and `source-storage-*.jsonl` sidecars retain decimal SQLite storage classes where needed. The 2 source view definitions remain in `.ingitdb/source-views.yaml` as metadata; they are not materialized collections.

The checked-in Git snapshot is the published inGitDB edition. [`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) records the DataTug version, binary hash, pinned source and record checksums, plus the independent parity receipt at [`ingitdb/native-parity-report.json`](ingitdb/native-parity-report.json). Its `prepared-not-hosted` status describes the generated bundle before repository publication and also covers BigQuery load files; it does not imply a hosted BigQuery service.

The published record format is DataTug's default JSON. To produce another edition from a verified, decoded copy of this pinned SQLite fixture, choose a **new** destination and pass `--records-format json` (default), `jsonl`, `ingr`, `csv`, or `yaml`:

```sh
datatug db export --from sqlite:///absolute/path/to/pinned-source.sqlite \
  --to ingitdb:///absolute/path/to/new-output --records-format json
```

The independent checker in `demo-db/websites/scripts/hosting-tools/validate_datatug_exports.py` compares the native schema and every typed row at its transport ID with this repository's pinned source. Run it from a checkout containing both repositories:

```sh
python3 ../websites/scripts/hosting-tools/validate_datatug_exports.py . ingitdb \
  --report /private/tmp/employees-ingitdb-parity.json
```

The source primary keys, foreign keys, UNIQUE and CHECK constraints, defaults, collations and SQL actions are preserved as source metadata; inGitDB does not enforce their full SQL behavior on later record edits. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).
