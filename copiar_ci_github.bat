@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Copiar CI de GitHub Actions (carpeta .github) ===
echo.

if not exist "github\android-apk.yml" (
  echo ERROR: No existe github\android-apk.yml
  pause
  exit /b 1
)

mkdir ".github\workflows" 2>nul
copy /Y "github\android-apk.yml" ".github\workflows\android-apk.yml"
if errorlevel 1 (
  echo ERROR al copiar el workflow
  pause
  exit /b 1
)
echo OK: .github\workflows\android-apk.yml

if exist "gitignore_plantilla.txt" (
  copy /Y "gitignore_plantilla.txt" ".gitignore"
  echo OK: .gitignore actualizado desde gitignore_plantilla.txt
) else (
  echo Aviso: no hay gitignore_plantilla.txt
)

echo.
echo Siguiente paso en Git Bash, PowerShell o CMD ^(desde esta carpeta^):
echo   git add -f .github/workflows/android-apk.yml
echo   git add -f .gitignore
echo   git commit -m "Agregar GitHub Actions para APK"
echo   git push
echo.
pause
