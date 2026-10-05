# Employees (browser edition)

A reproducible, browser-sized edition of the MySQL Employees sample database. This is a selected subset, not the complete upstream dataset. It contains 1,024 employees: IDs 10001–11000 plus every distinct manager ID in the source sample, all nine departments, all 24 manager assignments, and every department, title, and salary history row for the selected people. It retains the six native tables and both native views.

The upstream project says the sample data is fabricated and does not correspond to real people. Its `employees.sql` header credits MySQL AB (2007/2008), original data creators Fusheng Wang and Carlo Zaniolo, schema author Giuseppe Maxia, and XML conversion by Patrick Crews. The header licenses the work under CC BY-SA 3.0 Unported. This selected, adapted database and its derived model metadata are distributed under the same share-alike license; see [`LICENSE`](LICENSE).

The pinned upstream source and reproducible selection are documented in [`data-source/README.md`](data-source/README.md). Run `python3 scripts/fetch-source.py --destination /tmp/employees-source` to download and hash-check every required upstream file, then `python3 scripts/rebuild-source.py --source-dir /tmp/employees-source --check` to verify the checked-in compressed SQLite fixture. The converter preserves native table and view names, primary/unique keys and foreign keys, ISO dates, integer salary values, and exact text values. It does not invent rows or currency information.

The verified read-only OVDB mount provides record lookups and query access; writes remain disabled.
