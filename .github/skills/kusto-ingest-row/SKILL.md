---
name: kusto-ingest-row
description: "Ingest a single row into any table in the Kusto dev database using a PowerShell script. Takes the table name plus a set of field values, discovers the table's actual schema, matches fields to columns by name, serializes by column type, auto-fills datetime columns with current UTC time when omitted, and ingests other omitted columns as empty/null. USE FOR: kusto ingest, ingest row, ingest single row, write row to kusto, AgentPREvaluation, ingest into dev table, log row to kusto, record evaluation result"
---

# Ingest a single row into any Kusto table (dev database)

Ingests exactly one row into any table in the `dev` database using the bundled
PowerShell script. The script discovers the target table's schema, matches your
input fields to columns by name, and sends an inline ingestion control command.

## Target

- **Cluster:** `https://tacofund.westus2.kusto.windows.net`
- **Database:** `dev` (override with `-Database`)
- **Table:** supplied per call via `-Table`

## How it works

1. Queries the table schema (`<Table> | getschema`) to get column names, order, and types.
2. Matches each key in `-Data` to a column **by name, case-insensitive**.
3. Serializes each value to its Kusto column type:
   - `bool` -> `true`/`false` (accepts `$true`/`$false`, `true`/`false`, `1`/`0`, `yes`/`no`)
   - `datetime` -> ISO 8601 UTC (a `[datetime]` is converted to UTC; a string is passed through)
   - `int` / `long` / `real` / `decimal` -> invariant-culture numeric text
   - `dynamic` -> JSON (objects/hashtables are serialized; strings pass through)
   - `string` / `guid` / `timespan` / others -> text
4. Builds one CSV row in the table's column order and ingests via
   `.ingest inline into table <Table>`.

## Column coverage (missing columns allowed)

- Columns may be omitted from `-Data`.
- A **datetime** column with no supplied value is auto-filled with the current UTC time
  (convenient for `Timestamp`-style columns).
- Any other column with no supplied value is ingested as an empty/null field.
- Keys in `-Data` that do not match a column are reported as warnings and ignored.

## Prerequisites

- PowerShell 5.1+ or PowerShell 7+ on Windows.
- Azure authentication (the script auto-detects whichever is available):
  - Azure CLI: `az login`, **or**
  - Az PowerShell: `Connect-AzAccount`
- The signed-in identity must have **ingestor** (and **viewer**, for schema query)
  permission on the `dev` database.
- Outbound HTTPS to the cluster and the AAD login endpoint.

## Steps

1. Identify the target table and gather the field values for its columns.
2. Run the bundled script from the repo root:

   ```powershell
   .github\skills\kusto-ingest-row\scripts\Ingest-KustoRow.ps1 -Table "<TableName>" -Data @{
       Column1 = "<value>"
       Column2 = <value>
       # datetime columns may be omitted to auto-fill current UTC time
   }
   ```

3. Review the output: the script lists the columns it wrote. Omitted columns are
   reported (auto-filled or ingested as empty/null) and unknown keys are surfaced
   as warnings.

## Example: AgentPREvaluation

Schema: `Timestamp` (datetime), `SessionId` (string), `PRId` (string),
`PRLink` (string), `EvaluationResult` (bool), `EvaluationEvidence` (string).

```powershell
.github\skills\kusto-ingest-row\scripts\Ingest-KustoRow.ps1 -Table "AgentPREvaluation" -Data @{
    SessionId          = "abc-123"
    PRId               = "98765"
    PRLink             = "https://dev.azure.com/org/proj/_git/repo/pullrequest/98765"
    EvaluationResult   = $true
    EvaluationEvidence = "All checks passed."
    # Timestamp omitted -> auto-filled with current UTC time
}
```

## Notes

- Inline ingestion is for small, single-row writes. It is not for bulk loads.
- Values containing commas, quotes, or newlines are CSV-escaped automatically.
- Pass `-Cluster` or `-Database` only to override the defaults above.
