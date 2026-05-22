param(
  [switch]$PlanOnly,
  [switch]$DryRun,
  [switch]$SkipDeploy,
  [switch]$SkipSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$planMode = $PlanOnly -or $DryRun

$requiredProjectId = "western-pivot-452008-a6"
$cloudRunEnvDir = "infra/gcp/cloud-run"

function Resolve-EnvFile([string]$BaseName) {
  $localPath = Join-Path $cloudRunEnvDir ("{0}.env.local" -f $BaseName)
  $examplePath = Join-Path $cloudRunEnvDir ("{0}.env.example" -f $BaseName)

  if (Test-Path -LiteralPath $localPath) {
    return (Resolve-Path -LiteralPath $localPath).Path
  }
  if (Test-Path -LiteralPath $examplePath) {
    return (Resolve-Path -LiteralPath $examplePath).Path
  }

  throw "Missing env file: $localPath or $examplePath"
}

function Read-EnvFile([string]$PathValue) {
  $map = @{}
  $content = Get-Content -Raw -Encoding utf8 -LiteralPath $PathValue
  foreach ($line in ($content -split "`r?`n")) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line.TrimStart().StartsWith('#')) { continue }

    $index = $line.IndexOf('=')
    if ($index -le 0) { continue }

    $key = $line.Substring(0, $index).Trim()
    $value = $line.Substring($index + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    $map[$key] = $value
  }
  return $map
}

function Get-EnvValue([hashtable]$Map, [string]$Key, [string]$Default = "") {
  if ($Map.ContainsKey($Key) -and -not [string]::IsNullOrWhiteSpace([string]$Map[$Key])) {
    return [string]$Map[$Key]
  }
  return $Default
}

function ConvertTo-Bool([string]$Value, [bool]$Default = $false) {
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $Default
  }
  switch ($Value.Trim().ToLowerInvariant()) {
    "1" { return $true }
    "true" { return $true }
    "yes" { return $true }
    "on" { return $true }
    "0" { return $false }
    "false" { return $false }
    "no" { return $false }
    "off" { return $false }
    default { return $Default }
  }
}

function Test-SecretExists([string]$ProjectId, [string]$SecretName) {
  try {
    gcloud secrets describe $SecretName --project $ProjectId *> $null
    if ($LASTEXITCODE -eq 0) {
      return $true
    }
    return $false
  }
  catch {
    return $false
  }
}

function Join-KvList([hashtable]$Map, [string[]]$Keys) {
  $pairs = @()
  foreach ($key in $Keys) {
    if ($Map.ContainsKey($key)) {
      $pairs += ("{0}={1}" -f $key, [string]$Map[$key])
    }
  }
  return ($pairs -join ",")
}

function Show-Map([string]$Title, [hashtable]$Map, [string[]]$Keys) {
  Write-Host "`n$Title"
  foreach ($key in $Keys) {
    if ($Map.ContainsKey($key)) {
      Write-Host ("  {0}={1}" -f $key, [string]$Map[$key])
    }
  }
}

function Invoke-Health([string]$Url) {
  try {
    $resp = Invoke-WebRequest -Uri $Url -Method GET -TimeoutSec 45
    return [PSCustomObject]@{
      url = $Url
      status_code = [int]$resp.StatusCode
      ok = $true
      body = $resp.Content
    }
  }
  catch {
    $status = 0
    $body = ""
    if ($_.Exception.Response) {
      $status = [int]$_.Exception.Response.StatusCode
      $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
      $body = $reader.ReadToEnd()
    }
    return [PSCustomObject]@{
      url = $Url
      status_code = $status
      ok = $false
      body = $body
    }
  }
}

function Invoke-ChatSmoke([string]$Url) {
  $payload = @{
    message = "Compare public debt of Vietnam and Thailand from 2010 to 2023"
    conversationId = "cloud-smoke-phase14b"
  } | ConvertTo-Json -Depth 5

  try {
    $resp = Invoke-WebRequest -Uri $Url -Method POST -ContentType "application/json; charset=utf-8" -Body $payload -TimeoutSec 120
    return [PSCustomObject]@{
      url = $Url
      status_code = [int]$resp.StatusCode
      ok = $true
      body = $resp.Content
    }
  }
  catch {
    $status = 0
    $body = ""
    if ($_.Exception.Response) {
      $status = [int]$_.Exception.Response.StatusCode
      $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
      $body = $reader.ReadToEnd()
    }
    return [PSCustomObject]@{
      url = $Url
      status_code = $status
      ok = $false
      body = $body
    }
  }
}

$deployEnvPath = Resolve-EnvFile "deploy"
$backendEnvPath = Resolve-EnvFile "backend"
$aiAgentEnvPath = Resolve-EnvFile "ai-agent"

$deployEnv = Read-EnvFile $deployEnvPath
$backendEnv = Read-EnvFile $backendEnvPath
$aiAgentEnv = Read-EnvFile $aiAgentEnvPath

$projectId = Get-EnvValue $deployEnv "PROJECT_ID"
$region = Get-EnvValue $deployEnv "REGION"
$artifactRepository = Get-EnvValue $deployEnv "ARTIFACT_REPOSITORY"
$imageTag = Get-EnvValue $deployEnv "IMAGE_TAG"
$backendServiceName = Get-EnvValue $deployEnv "BACKEND_SERVICE_NAME"
$aiAgentServiceName = Get-EnvValue $deployEnv "AI_AGENT_SERVICE_NAME"
$runtimeServiceAccount = Get-EnvValue $deployEnv "RUNTIME_SERVICE_ACCOUNT"
$backendImageName = Get-EnvValue $deployEnv "BACKEND_IMAGE_NAME"
$aiAgentImageName = Get-EnvValue $deployEnv "AI_AGENT_IMAGE_NAME"

if ([string]::IsNullOrWhiteSpace($projectId) -or [string]::IsNullOrWhiteSpace($region)) {
  throw "PROJECT_ID and REGION are required in $deployEnvPath"
}
if ($projectId -ne $requiredProjectId) {
  throw "PROJECT_ID must be exactly $requiredProjectId"
}

$activeProject = (gcloud config get-value project).Trim()
if ($activeProject -ne $projectId) {
  throw "Active gcloud project mismatch: expected $projectId, got $activeProject"
}

$schedulerVerifyCommand = "gcloud scheduler jobs describe economic-data-pipeline-monthly --location $region --project $projectId --format=`"value(state)`""
$schedulerState = "not verified"
try {
  $schedulerState = (gcloud scheduler jobs describe economic-data-pipeline-monthly --location $region --project $projectId --format="value(state)").Trim()
}
catch {
  $schedulerState = "not verified"
}

$backendImage = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $region, $projectId, $artifactRepository, $backendImageName, $imageTag
$aiAgentImage = "{0}-docker.pkg.dev/{1}/{2}/{3}:{4}" -f $region, $projectId, $artifactRepository, $aiAgentImageName, $imageTag

$secretNames = @{
  internal = "gov-ai-agent-internal-api-key"
  gemini = "gov-ai-gemini-api-key"
  parserBase = "gov-ai-parser-service-base-url"
  parserApi = "gov-ai-parser-service-api-key"
}

$secretExists = @{
  ($secretNames.internal) = (Test-SecretExists -ProjectId $projectId -SecretName $secretNames.internal)
  ($secretNames.gemini) = (Test-SecretExists -ProjectId $projectId -SecretName $secretNames.gemini)
  ($secretNames.parserBase) = (Test-SecretExists -ProjectId $projectId -SecretName $secretNames.parserBase)
  ($secretNames.parserApi) = (Test-SecretExists -ProjectId $projectId -SecretName $secretNames.parserApi)
}

$enableGemini = ConvertTo-Bool (Get-EnvValue $aiAgentEnv "ENABLE_GEMINI" "true") $true
$parserRequired = ConvertTo-Bool (Get-EnvValue $aiAgentEnv "PARSER_SERVICE_REQUIRED" "false") $false
$parserApiKeyRuntimeUsed = ConvertTo-Bool (Get-EnvValue $aiAgentEnv "PARSER_SERVICE_API_KEY_RUNTIME_USED" "false") $false

$backendNonSecretKeys = @(
  "NODE_ENV",
  "BACKEND_DATA_SOURCE",
  "BIGQUERY_PROJECT_ID",
  "BIGQUERY_LOCATION",
  "BIGQUERY_GOLD_DATASET",
  "BIGQUERY_ANALYTICS_DATASET",
  "BIGQUERY_MAX_BYTES_BILLED",
  "BIGQUERY_CACHE_TTL_SECONDS",
  "AI_AGENT_BASE_URL",
  "AI_AGENT_TIMEOUT_MS"
)
$aiAgentNonSecretKeys = @(
  "ENVIRONMENT",
  "APP_ENV",
  "PYTHONUNBUFFERED",
  "AI_AGENT_DATA_SOURCE",
  "BIGQUERY_PROJECT_ID",
  "BIGQUERY_LOCATION",
  "BIGQUERY_GOLD_DATASET",
  "BIGQUERY_ANALYTICS_DATASET",
  "BIGQUERY_MAX_BYTES_BILLED",
  "ENABLE_GEMINI"
)

$agentSecretBindings = @(
  "INTERNAL_API_KEY=$($secretNames.internal):latest",
  "GEMINI_API_KEY=$($secretNames.gemini):latest"
)
if ($secretExists[$secretNames.parserBase]) {
  $agentSecretBindings += "PARSER_SERVICE_BASE_URL=$($secretNames.parserBase):latest"
}
if ($parserApiKeyRuntimeUsed -and $secretExists[$secretNames.parserApi]) {
  $agentSecretBindings += "PARSER_SERVICE_API_KEY=$($secretNames.parserApi):latest"
}

$backendSecretBindings = @(
  "AI_AGENT_INTERNAL_API_KEY=$($secretNames.internal):latest"
)

Write-Host "=== Cloud Run Deploy Plan (Sanitized) ==="
Write-Host "deploy env file: $deployEnvPath"
Write-Host "backend env file: $backendEnvPath"
Write-Host "ai-agent env file: $aiAgentEnvPath"
Write-Host "project: $projectId"
Write-Host "active_project: $activeProject"
Write-Host "region: $region"
Write-Host "backend_service: $backendServiceName"
Write-Host "ai_agent_service: $aiAgentServiceName"
Write-Host "runtime_service_account: $runtimeServiceAccount"
Write-Host "backend_image: $backendImage"
Write-Host "ai_agent_image: $aiAgentImage"
Write-Host "scheduler_verify_command: $schedulerVerifyCommand"
Write-Host "scheduler_state: $schedulerState"

Show-Map "backend non-secret env (for --set-env-vars)" $backendEnv $backendNonSecretKeys
Show-Map "ai-agent non-secret env (for --set-env-vars)" $aiAgentEnv $aiAgentNonSecretKeys

Write-Host "`nsecret existence (name only):"
foreach ($entry in $secretExists.GetEnumerator()) {
  $status = if ($entry.Value) { "present" } else { "missing" }
  Write-Host "  $($entry.Key): $status"
}

Write-Host "`nbackend --set-secrets:"
foreach ($binding in $backendSecretBindings) {
  Write-Host "  $binding"
}
Write-Host "ai-agent --set-secrets:"
foreach ($binding in $agentSecretBindings) {
  Write-Host "  $binding"
}

$backendEnvCsv = Join-KvList -Map $backendEnv -Keys $backendNonSecretKeys
$agentEnvCsv = Join-KvList -Map $aiAgentEnv -Keys $aiAgentNonSecretKeys
$backendSecretsCsv = ($backendSecretBindings -join ",")
$agentSecretsCsv = ($agentSecretBindings -join ",")

Write-Host "`nsanitzed commands preview:"
Write-Host "  gcloud run deploy $aiAgentServiceName --project $projectId --region $region --image $aiAgentImage --set-env-vars <non-secret-csv> --set-secrets <secret-names-only>"
Write-Host "  gcloud run deploy $backendServiceName --project $projectId --region $region --image $backendImage --set-env-vars <non-secret-csv> --set-secrets <secret-names-only>"

if ($planMode) {
  Write-Host "`nPlan mode enabled. No deploy/update/smoke was executed."
  return
}

if ($schedulerState -ne "PAUSED") {
  throw "Hard stop: Scheduler state must be PAUSED. Current state: $schedulerState"
}
if (-not $secretExists[$secretNames.internal]) {
  throw "Hard stop: missing required secret $($secretNames.internal)"
}
if ($enableGemini -and -not $secretExists[$secretNames.gemini]) {
  throw "Hard stop: ENABLE_GEMINI=true but missing required secret $($secretNames.gemini)"
}
if ($parserRequired -and -not $secretExists[$secretNames.parserBase]) {
  throw "Hard stop: parser runtime requires $($secretNames.parserBase) but it is missing"
}
if ($parserRequired -and $parserApiKeyRuntimeUsed -and -not $secretExists[$secretNames.parserApi]) {
  throw "Hard stop: parser API key runtime is enabled but secret $($secretNames.parserApi) is missing"
}

if ($SkipDeploy) {
  Write-Host "SkipDeploy=true, deploy step skipped."
  return
}

$commonFlags = @(
  "--project", $projectId,
  "--region", $region,
  "--platform", "managed",
  "--service-account", $runtimeServiceAccount,
  "--ingress", "all",
  "--allow-unauthenticated",
  "--min-instances", "0",
  "--cpu", "1",
  "--memory", "1Gi"
)

gcloud run deploy $aiAgentServiceName @commonFlags --image $aiAgentImage --set-env-vars $agentEnvCsv --set-secrets $agentSecretsCsv

$agentUrl = (gcloud run services describe $aiAgentServiceName --region $region --project $projectId --format="value(status.url)").Trim()
if (-not $backendEnv.ContainsKey("AI_AGENT_BASE_URL") -or [string]::IsNullOrWhiteSpace([string]$backendEnv["AI_AGENT_BASE_URL"])) {
  $backendEnv["AI_AGENT_BASE_URL"] = $agentUrl
  $backendEnvCsv = Join-KvList -Map $backendEnv -Keys $backendNonSecretKeys
}

gcloud run deploy $backendServiceName @commonFlags --image $backendImage --set-env-vars $backendEnvCsv --set-secrets $backendSecretsCsv

$backendUrl = (gcloud run services describe $backendServiceName --region $region --project $projectId --format="value(status.url)").Trim()

Write-Host "`nDeploy finished"
Write-Host "ai_agent_url: $agentUrl"
Write-Host "backend_url: $backendUrl"

if ($SkipSmoke) {
  Write-Host "SkipSmoke=true, smoke step skipped."
  return
}

$agentHealth = Invoke-Health "$agentUrl/health"
$backendAiHealth = Invoke-Health "$backendUrl/api/v1/ai/health"
$backendChat = Invoke-ChatSmoke "$backendUrl/api/v1/ai/chat"
$backendCompare = Invoke-Health "$backendUrl/api/v1/compare?countries=VNM,THA&indicator=govdebt_GDP&from=2010&to=2023"
$backendCountryIndicators = Invoke-Health "$backendUrl/api/v1/countries/AFG/indicators"

$smokeResult = [ordered]@{
  ai_agent_health = $agentHealth
  backend_ai_health = $backendAiHealth
  backend_chat = $backendChat
  backend_compare = $backendCompare
  backend_country_indicators = $backendCountryIndicators
}

Write-Host "`n=== Smoke Results (JSON) ==="
$smokeResult | ConvertTo-Json -Depth 8

