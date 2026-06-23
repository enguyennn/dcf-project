<#
.SYNOPSIS
    Ingests a single row into any table in the Kusto "dev" database.

.DESCRIPTION
    Generic single-row Kusto ingestion. Given a target table name and a set of
    field values (as a hashtable keyed by column name), the script:

      1. Queries the table's actual schema (column names, ordinals, and types).
      2. Matches the provided fields to columns by name (case-insensitive).
      3. Serializes each value according to its Kusto column type (bool, datetime,
         int, long, real, decimal, string, guid, dynamic, timespan).
      4. Ingests one row via inline ingestion (a control command sent to the
         cluster management endpoint), respecting the table's column order.

    Column coverage rules (missing columns are allowed):
      - A datetime column with no supplied value is auto-populated with the
        current UTC time (convenient for "Timestamp"-style columns).
      - Any other column with no supplied value is ingested as an empty/null
        field, so it is fine to omit columns from -Data.
      - Keys in -Data that do not match a column are reported and ignored.

.PARAMETER Table
    The target table name in the database.

.PARAMETER Data
    A hashtable of column-name = value pairs. Keys are matched to table columns
    case-insensitively. Datetime columns may be omitted to auto-fill UTC now.

.PARAMETER Cluster
    The Kusto cluster URL. Defaults to the dev cluster.

.PARAMETER Database
    The Kusto database name. Defaults to "dev".

.EXAMPLE
    ./Ingest-KustoRow.ps1 -Table "AgentPREvaluation" -Data @{
        SessionId          = "abc-123"
        PRId               = "98765"
        PRLink             = "https://dev.azure.com/org/proj/_git/repo/pullrequest/98765"
        EvaluationResult   = $true
        EvaluationEvidence = "All checks passed."
        # Timestamp omitted -> auto-filled with current UTC time
    }

.EXAMPLE
    ./Ingest-KustoRow.ps1 -Table "MyOtherTable" -Data @{
        Id    = 42
        Name  = "example"
        Score = 3.14
    }
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Table,

    [Parameter(Mandatory = $true)]
    [ValidateNotNull()]
    [hashtable]$Data,

    [Parameter(Mandatory = $false)]
    [string]$Cluster = "https://tacofund.westus2.kusto.windows.net",

    [Parameter(Mandatory = $false)]
    [string]$Database = "dev"
)

$ErrorActionPreference = "Stop"
$invariant = [System.Globalization.CultureInfo]::InvariantCulture

function ConvertTo-CsvField {
    param([string]$Value)
    if ($null -eq $Value) { $Value = "" }
    # CSV-escape: wrap in double quotes and double any embedded double quotes.
    return '"' + ($Value -replace '"', '""') + '"'
}

function Get-KustoAccessToken {
    param([string]$Resource)

    # Prefer Azure CLI if available and logged in.
    $azCli = Get-Command az -ErrorAction SilentlyContinue
    if ($azCli) {
        try {
            $token = (az account get-access-token --resource $Resource --query accessToken -o tsv 2>$null)
            if ($token) { return $token.Trim() }
        }
        catch {
            Write-Verbose "Azure CLI token acquisition failed: $($_.Exception.Message)"
        }
    }

    # Fall back to Az PowerShell module.
    $getAzToken = Get-Command Get-AzAccessToken -ErrorAction SilentlyContinue
    if ($getAzToken) {
        try {
            $azToken = Get-AzAccessToken -ResourceUrl $Resource -ErrorAction Stop
            $rawToken = $azToken.Token
            if ($rawToken -is [System.Security.SecureString]) {
                $rawToken = [System.Net.NetworkCredential]::new("", $rawToken).Password
            }
            if ($rawToken) { return $rawToken }
        }
        catch {
            Write-Verbose "Az PowerShell token acquisition failed: $($_.Exception.Message)"
        }
    }

    throw "Unable to acquire an access token. Run 'az login' (Azure CLI) or 'Connect-AzAccount' (Az PowerShell) and retry."
}

function Invoke-KustoRest {
    param(
        [string]$Resource,
        [string]$Endpoint,   # "query" or "mgmt"
        [string]$Db,
        [string]$Csl,
        [string]$AccessToken
    )
    $uri = "$Resource/v1/rest/$Endpoint"
    $body = @{ db = $Db; csl = $Csl } | ConvertTo-Json -Depth 4
    $headers = @{
        Authorization  = "Bearer $AccessToken"
        "Content-Type" = "application/json; charset=utf-8"
        Accept         = "application/json"
    }
    return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body
}

function Format-KustoValue {
    param($Value, [string]$KustoType)

    switch ($KustoType.ToLowerInvariant()) {
        "bool" {
            if ($Value -is [bool]) { return ($(if ($Value) { "true" } else { "false" })) }
            $s = "$Value".Trim().ToLowerInvariant()
            if ($s -in @("true", "1", "yes", "y")) { return "true" }
            if ($s -in @("false", "0", "no", "n")) { return "false" }
            throw "Value '$Value' is not a valid boolean."
        }
        "datetime" {
            if ($Value -is [datetime]) {
                return ([datetime]$Value).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ")
            }
            return "$Value"
        }
        "int"     { return [System.Convert]::ToInt32($Value).ToString($invariant) }
        "long"    { return [System.Convert]::ToInt64($Value).ToString($invariant) }
        "real"    { return [System.Convert]::ToDouble($Value).ToString($invariant) }
        "decimal" { return [System.Convert]::ToDecimal($Value).ToString($invariant) }
        "dynamic" {
            if ($Value -is [string]) { return $Value }
            return ($Value | ConvertTo-Json -Compress -Depth 10)
        }
        default { return "$Value" }   # string, guid, timespan, etc.
    }
}

# --- 1. Acquire token ---
$resource = $Cluster.TrimEnd("/")
$accessToken = Get-KustoAccessToken -Resource $resource

# --- 2. Discover the table schema (ordered by column ordinal) ---
$schemaCsl = "$Table | getschema | project ColumnName, ColumnType, ColumnOrdinal | sort by ColumnOrdinal asc"
$schemaResp = Invoke-KustoRest -Resource $resource -Endpoint "query" -Db $Database -Csl $schemaCsl -AccessToken $accessToken

$schemaRows = $schemaResp.Tables[0].Rows
if (-not $schemaRows -or $schemaRows.Count -eq 0) {
    throw "Table '$Table' was not found in database '$Database', or it has no columns."
}

$columns = foreach ($row in $schemaRows) {
    [PSCustomObject]@{ Name = [string]$row[0]; Type = [string]$row[1] }
}

# --- 3. Warn about unknown keys in -Data ---
$columnNameSet = @{}
foreach ($c in $columns) { $columnNameSet[$c.Name.ToLowerInvariant()] = $c.Name }
foreach ($key in $Data.Keys) {
    if (-not $columnNameSet.ContainsKey("$key".ToLowerInvariant())) {
        Write-Warning "Field '$key' does not match any column in '$Table' and will be ignored."
    }
}

# Build a case-insensitive lookup of provided values.
$providedByLower = @{}
foreach ($key in $Data.Keys) { $providedByLower["$key".ToLowerInvariant()] = $Data[$key] }

# --- 4. Build the CSV row in the table's column order ---
$csvFields = @()
foreach ($col in $columns) {
    $lower = $col.Name.ToLowerInvariant()
    $hasValue = $providedByLower.ContainsKey($lower)
    $rawValue = if ($hasValue) { $providedByLower[$lower] } else { $null }

    $isEmpty = (-not $hasValue) -or ($null -eq $rawValue) -or `
        (($rawValue -isnot [bool]) -and [string]::IsNullOrWhiteSpace("$rawValue"))

    if ($isEmpty) {
        if ($col.Type.ToLowerInvariant() -eq "datetime") {
            $rawValue = [DateTime]::UtcNow
            Write-Host "Column '$($col.Name)' (datetime) not supplied; using current UTC time."
        }
        else {
            # Missing/empty non-datetime column -> ingest an empty (null) field.
            Write-Host "Column '$($col.Name)' not supplied; ingesting an empty/null value."
            $csvFields += ""
            continue
        }
    }

    $formatted = Format-KustoValue -Value $rawValue -KustoType $col.Type
    $csvFields += (ConvertTo-CsvField $formatted)
}
$csvRow = $csvFields -join ","

# --- 5. Ingest one row ---
$command = ".ingest inline into table $Table <|`n$csvRow"
Write-Host "Ingesting 1 row into [$Database].[$Table] on $resource ..."
$null = Invoke-KustoRest -Resource $resource -Endpoint "mgmt" -Db $Database -Csl $command -AccessToken $accessToken

Write-Host "Ingestion command accepted. Columns written:"
foreach ($col in $columns) { Write-Host "  - $($col.Name) [$($col.Type)]" }
