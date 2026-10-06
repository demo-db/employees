# Employees (browser edition)

A reproducible, browser-sized edition of the MySQL Employees sample database. This is a selected subset, not the complete upstream dataset. It contains 1,024 employees: IDs 10001–11000 plus every distinct manager ID in the source sample, all nine departments, all 24 manager assignments, and every department, title, and salary history row for the selected people. It retains the six native tables and both native views.

The upstream project says the sample data is fabricated and does not correspond to real people. Its `employees.sql` header credits MySQL AB (2007/2008), original data creators Fusheng Wang and Carlo Zaniolo, schema author Giuseppe Maxia, and XML conversion by Patrick Crews. The header licenses the work under CC BY-SA 3.0 Unported. This selected, adapted database and its derived model metadata are distributed under the same share-alike license; see [`LICENSE`](LICENSE).

The pinned upstream source and reproducible selection are documented in [`data-source/README.md`](data-source/README.md). Run `python3 scripts/fetch-source.py --destination /tmp/employees-source` to download and hash-check every required upstream file, then `python3 scripts/rebuild-source.py --source-dir /tmp/employees-source --check` to verify the checked-in compressed SQLite fixture. The converter preserves native table and view names, primary/unique keys and foreign keys, ISO dates, integer salary values, and exact text values. It does not invent rows or currency information.

The verified read-only OVDB mount provides record lookups and query access; writes remain disabled.

## Native inGitDB snapshot

The `ingitdb/` directory contains 13,584 source table rows across 6 collections. It is a Git-backed, queryable snapshot prepared from the pinned SQLite fixture. Verify and query it with the installed inGitDB CLI:

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from departments_fc3bfaae --limit 1 --format json
```

[`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) maps each native table to its collection, row count, original primary and foreign keys, column types, transport encodings, and SHA-256 of its record file. The source fixture SHA-256 is `46b49dd0e141cd8db66d57680a10febfccc15e6f54dc7b8f3c2316b55e11c5f0`. These bytes were exported against provider commit `2069e26e8fdb60bdb16507f75569a579cf3da7cf`; the source fixture hash also matches this repository's pinned fixture. Record keys encode native primary keys where present; keyless tables use stable ordinal IDs, which are not native keys. Native `primary_key` names the source key columns while encoded record IDs remain the transport keys. inGitDB validates safe transported column types and required fields; `exportRequired` can be stricter than SQLite declaration for nullable primary keys. The export manifest preserves source SQL, ordered indexes and foreign-key groups with actions, defaults, and declared nullability. Foreign keys and SQL uniqueness, CHECK, collation, default, and action behavior are source metadata here, not constraints enforced by inGitDB. Exact decimal values travel as strings and binary values as base64 where marked in column metadata. Source view definitions are retained as metadata only; they are not materialized in inGitDB. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).
