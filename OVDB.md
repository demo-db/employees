---
ovdb: 1
publish:
  - ./ovdb.yaml
  - ./ovdb-database.json
---

# OpenVaultDB publication

This repository publishes the Employees browser-edition descriptor and metadata for a reproducible subset of the MySQL Employees sample. The descriptor preserves the six native table names and both source view definitions; it identifies the edition as a selected subset rather than the complete upstream database.

Read and static export metadata are published with the provider. OVDB read and query access are available through the verified read-only mount; write access remains disabled. The source-derived database and schema metadata are licensed CC BY-SA 3.0; see `LICENSE` for terms and attribution.
