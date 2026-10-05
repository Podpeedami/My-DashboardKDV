param(
  [Parameter(Mandatory=$true)] [string]$GitHubRepo
)

$ErrorActionPreference = 'Stop'

if ($GitHubRepo -notmatch '^https://github\.com/[^/]+/[^/]+/?$') {
  throw 'Укажи репозиторий в формате https://github.com/USER/REPO'
}

$ownerRepo = $GitHubRepo.TrimEnd('/') -replace '^https://github\.com/', ''
$owner = ($ownerRepo -split '/')[0]
$repo = ($ownerRepo -split '/')[1]

(Get-Content docker-compose.yml -Raw).Replace('YOUR_GITHUB_USERNAME', $owner) | Set-Content docker-compose.yml -Encoding UTF8

if (-not (Test-Path .git)) { git init }
git branch -M main
git add .
git commit -m 'My DashboardKDV 4.5 release' 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host 'Нет новых изменений для коммита.' }
git remote remove origin 2>$null
if ($LASTEXITCODE -ne 0) { $global:LASTEXITCODE = 0 }
git remote add origin $GitHubRepo

git push -u origin main
Write-Host "Готово. GitHub Actions теперь соберёт образ ghcr.io/$owner/my-dashboardkdv:latest"
