param(
  [string]$SecretsEnvFile = "infra/gcp/cloud-run/secrets.env.local"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

function Get-ResolvedPathOrNull([string]$PathValue) {
  if ([System.IO.Path]::IsPathRooted($PathValue)) {
    if (Test-Path -LiteralPath $PathValue) {
      return (Resolve-Path -LiteralPath $PathValue).Path
    }
    return $null
  }

  $candidate = Join-Path (Get-Location) $PathValue
  if (Test-Path -LiteralPath $candidate) {
    return (Resolve-Path -LiteralPath $candidate).Path
  }
  return $null
}

function Read-EnvFile([string]$PathValue) {
  $map = @{}
  $content = Get-Content -Raw -Encoding utf8 -LiteralPath $PathValue
  foreach ($line in ($content -split "`r?`n")) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line.TrimStart().StartsWith('#')) { continue }
    $idx = $line.IndexOf('=')
    if ($idx -lt 1) { continue }
    $key = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    $map[$key] = $value
  }
  return $map
}

$deployLocal = "infra/gcp/cloud-run/deploy.env.local"
$deployExample = "infra/gcp/cloud-run/deploy.env.example"
$deployPath = Get-ResolvedPathOrNull $deployLocal
if (-not $deployPath) {
  $deployPath = Get-ResolvedPathOrNull $deployExample
}
if (-not $deployPath) {
  throw "Missing deploy env file: $deployLocal or $deployExample"
}

$secretsPath = Get-ResolvedPathOrNull $SecretsEnvFile
if (-not $secretsPath) {
  throw "Missing secrets env file: $SecretsEnvFile"
}

$deployEnv = Read-EnvFile $deployPath
$secretsEnv = Read-EnvFile $secretsPath

$projectId = [string]$deployEnv["PROJECT_ID"]
if ([string]::IsNullOrWhiteSpace($projectId)) {
  throw "PROJECT_ID is missing in $deployPath"
}

$activeProject = (gcloud config get-value project).Trim()
if ($activeProject -ne $projectId) {
  throw "Active gcloud project mismatch: expected $projectId, got $activeProject"
}

function Add-SecretVersionFromEnv([string]$EnvKey, [string]$SecretName) {
  $value = [string]$secretsEnv[$EnvKey]
  if ([string]::IsNullOrWhiteSpace($value)) {
    Write-Host "skip $SecretName ($EnvKey is empty)"
    return
  }

  gcloud secrets describe $SecretName --project $projectId *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "create $SecretName"
    gcloud secrets create $SecretName --project $projectId --replication-policy automatic *> $null
  }

  $tmpFile = [System.IO.Path]::GetTempFileName()
  try {
    Set-Content -LiteralPath $tmpFile -Value $value -Encoding utf8 -NoNewline
    gcloud secrets versions add $SecretName --project $projectId --data-file $tmpFile *> $null
    Write-Host "updated $SecretName (new version added)"
  }
  finally {
    Remove-Item -LiteralPath $tmpFile -Force -ErrorAction SilentlyContinue
  }
}

Add-SecretVersionFromEnv "GEMINI_API_KEY" "gov-ai-gemini-api-key"
Add-SecretVersionFromEnv "AI_AGENT_INTERNAL_API_KEY" "gov-ai-agent-internal-api-key"
Add-SecretVersionFromEnv "PARSER_SERVICE_BASE_URL" "gov-ai-parser-service-base-url"
Add-SecretVersionFromEnv "PARSER_SERVICE_API_KEY" "gov-ai-parser-service-api-key"

Write-Host "Secret import completed without printing secret values."
