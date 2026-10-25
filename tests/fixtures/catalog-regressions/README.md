# Frozen importer regression inputs

Minimal product documents/rows from the original Microsoft_Resources snapshot
`f69e23f8bf478004d45abd56757674155b1ece0a` (2025-10-09).
Only title, source URL and version evidence are retained. Windows 7 keeps rows
0–1 (mismatched x86 metadata/x64 download); win11-arm keeps rows 3–4
(22H2/21H2 64ARM filenames). Office and Server 2025 retain locale groups.
These fixtures deliberately do not refresh with the live catalog: they preserve
known source quirks without requiring today's upstream to keep historical rows.
Original source files remain unchanged.
