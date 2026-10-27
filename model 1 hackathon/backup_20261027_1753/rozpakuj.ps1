# Podmiana projektu na najnowszy zip z Pobranych – z kopia zapasowa.
# Uruchom W FOLDERZE PROJEKTU (tam, gdzie jest main.py):
#     powershell -ExecutionPolicy Bypass -File rozpakuj.ps1
# albo wskaz projekt:  ... -File rozpakuj.ps1 -Projekt "C:\sciezka\do\projektu"
# Nigdy nie tworzy nowego folderu i nie usuwa plikow. Dane, .venv, .git, .idea, cache, wyniki, modele zostaja.

param(
    [string]$Projekt = (Get-Location).Path,
    [string]$Pobrane = "$env:USERPROFILE\Downloads"
)

if (-not (Test-Path (Join-Path $Projekt "main.py"))) {
    Write-Host "W '$Projekt' nie ma main.py - to nie jest folder projektu. Uruchom skrypt w folderze projektu albo podaj -Projekt." -ForegroundColor Red
    return
}
$zip = Get-ChildItem "$Pobrane\model_predykcyjny_hackathon_oczyszczalnie_sciekow*.zip" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { Write-Host "Nie znaleziono zipa w $Pobrane" -ForegroundColor Red; return }
Write-Host "Projekt: $Projekt" -ForegroundColor Cyan
Write-Host "Zip:     $($zip.Name)  ($($zip.LastWriteTime))" -ForegroundColor Cyan
if (Test-Path (Join-Path $Projekt ".git")) { Write-Host "Repozytorium git: tak (.git nie jest ruszany)" -ForegroundColor Cyan }

# 1. rozpakowanie do folderu tymczasowego
$tmp = Join-Path $env:TEMP "smartwater_rozpak"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $zip.FullName -DestinationPath $tmp -Force
$zrodlo = Join-Path $tmp "model_predykcyjny_hackathon_oczyszczalnie_sciekow"
if (-not (Test-Path $zrodlo)) { Write-Host "W zipie nie ma folderu programu" -ForegroundColor Red; return }

# 2. kopia zapasowa kodu (bez danych, venv, gita, cache, wynikow i modelu)
$bak = Join-Path (Split-Path $Projekt) ("backup_" + (Get-Date -Format "yyyyMMdd_HHmm"))
robocopy $Projekt $bak /E /XD Dane .venv .git .idea cache wyniki modele __pycache__ .pytest_cache backup_* /NFL /NDL /NJH /NJS /NP | Out-Null
Write-Host "Kopia zapasowa: $bak" -ForegroundColor Cyan

# 3. podmiana – tylko dokladanie / nadpisywanie plikow z zipa (bez usuwania), wypisuje zmienione pliki
robocopy $zrodlo $Projekt /E /XD .git /NDL /NJH /NJS /NP
Remove-Item $tmp -Recurse -Force

# 4. jaka wersja weszla
$w = Join-Path $Projekt "WERSJA.txt"
if (Test-Path $w) { Write-Host "`n--- WERSJA ---" -ForegroundColor Green; Get-Content $w }
Write-Host "`nDalej: .\.venv\Scripts\Activate.ps1 ; python main.py aplikacja" -ForegroundColor Cyan
