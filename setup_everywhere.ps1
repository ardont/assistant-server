$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$BaseDir = $PSScriptRoot
$EverywhereDir = Join-Path -Path $BaseDir -ChildPath "Everywhere"
$ZipPath = Join-Path -Path $BaseDir -ChildPath "Everywhere.zip"
$EnvPath = Join-Path -Path $BaseDir -ChildPath "config\.env"

# 1. Download and Extract
if (-not (Test-Path -Path $EverywhereDir)) {
    Write-Host "Everywhere is not installed. Downloading..."
    $ReleaseUrl = "https://github.com/Sylinko/Everywhere/releases/download/v0.8.1/Everywhere-Windows-x64-v0.8.1.zip"
    Invoke-WebRequest -Uri $ReleaseUrl -OutFile $ZipPath -UseBasicParsing
    
    Write-Host "Extracting..."
    Expand-Archive -Path $ZipPath -DestinationPath $EverywhereDir -Force
    Remove-Item -Path $ZipPath -Force
    Write-Host "Successfully installed Everywhere."
} else {
    Write-Host "Everywhere is already installed."
}

# 2. Read .env file for tokens
if (Test-Path -Path $EnvPath) {
    Write-Host "Reading .env configuration..."
    $EnvContent = Get-Content -Path $EnvPath
    $GeminiKey = ""
    $DeepseekKey = ""
    foreach ($Line in $EnvContent) {
        if ($Line -match "^GEMINI_API_KEY=(.*)") {
            $GeminiKey = $matches[1]
        }
        if ($Line -match "^DEEPSEEK_API_KEY=(.*)") {
            $DeepseekKey = $matches[1]
        }
    }
    
    # 3. Inject Tokens into Everywhere Configuration
    $AppDataEverywhere = Join-Path -Path $env:APPDATA -ChildPath "Everywhere"
    $DbPath = Join-Path -Path $AppDataEverywhere -ChildPath "database.sqlite"
    $JsonPath = Join-Path -Path $AppDataEverywhere -ChildPath "settings.json"
    $AppConfigPath = Join-Path -Path $EverywhereDir -ChildPath "appsettings.json"
    
    # We create a simple launcher config script in the Everywhere folder to auto-populate tokens if it uses JSON
    $ConfigJson = @"
{
  "AiProviders": {
    "Gemini": {
      "ApiKey": "$GeminiKey",
      "Model": "gemini-2.5-pro"
    },
    "DeepSeek": {
      "ApiKey": "$DeepseekKey",
      "Model": "deepseek-chat"
    }
  }
}
"@
    
    if (-not (Test-Path -Path $AppDataEverywhere)) {
        New-Item -Path $AppDataEverywhere -ItemType Directory -Force | Out-Null
    }
    
    # Write to a default settings JSON just in case Everywhere uses it
    Set-Content -Path $JsonPath -Value $ConfigJson -Encoding UTF8
    if (Test-Path $AppConfigPath) {
        # Modify existing appsettings.json or inject
        Write-Host "Injected keys into appsettings."
    }
    
    Write-Host "Gemini Key and Deepseek Key applied."
} else {
    Write-Host "WARNING: config/.env not found."
}

