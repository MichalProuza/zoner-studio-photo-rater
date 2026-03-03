param(
    [string]$SourceDir = 'C:\Users\michal.prouza\Pictures\2025-10 Survivor\2025-10-30',
    [string]$PreviewDir = 'C:\Users\michal.prouza\Pictures\2025-10 Survivor\2025-10-30\_previews',
    [string]$RatingsPath = 'C:\Users\michal.prouza\Pictures\2025-10 Survivor\2025-10-30\ratings.json',
    [string]$CatalogPath = 'C:\Users\michal.prouza\AppData\Local\Zoner\ZPS X\ZPSCatalog\index.catalogue-zps',
    [switch]$Recursive,
    [switch]$DryRun,
    [int]$MaxSize = 800
)

$ErrorActionPreference = 'Stop'

Write-Host '== ZPS X Photo Rater workflow ==' -ForegroundColor Cyan
Write-Host "SourceDir:   $SourceDir"
Write-Host "PreviewDir:  $PreviewDir"
Write-Host "RatingsPath: $RatingsPath"
Write-Host "CatalogPath: $CatalogPath"

if (!(Test-Path $SourceDir)) {
    throw "SourceDir neexistuje: $SourceDir"
}

if (!(Test-Path $RatingsPath)) {
    Write-Host "ratings.json nenalezen, vytvářím prázdný soubor: $RatingsPath" -ForegroundColor Yellow
    '{}' | Set-Content -Path $RatingsPath -Encoding UTF8
}

$extractCmd = @('python', 'scripts/extract_previews.py', $SourceDir, '--output', $PreviewDir, '--max-size', "$MaxSize")
if ($Recursive) { $extractCmd += '--recursive' }

Write-Host "`n[1/2] Extrakce náhledů..." -ForegroundColor Green
& $extractCmd[0] $extractCmd[1..($extractCmd.Count - 1)]

Write-Host "`nNyní ohodnoť náhledy dle prompts/RATING_PROMPT_V2.md a ulož výsledky do: $RatingsPath" -ForegroundColor Yellow
Read-Host 'Až bude ratings.json připravený, stiskni Enter pro pokračování k zápisu hodnocení'

$applyCmd = @('python', 'scripts/apply_ratings.py', $RatingsPath, '--catalog', $CatalogPath)
if ($DryRun) { $applyCmd += '--dry-run' }

Write-Host "`n[2/2] Aplikace hodnocení do katalogu..." -ForegroundColor Green
& $applyCmd[0] $applyCmd[1..($applyCmd.Count - 1)]

Write-Host "`nHotovo." -ForegroundColor Cyan
