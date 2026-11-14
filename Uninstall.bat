@echo off
chcp 65001 >nul
if not exist "%~dp0BallxPit_RU_Font.exe" (
  echo Рядом нет BallxPit_RU_Font.exe. Распакуй архив целиком и запусти Uninstall.bat из распакованной папки.
  echo Если exe пропадает сразу после распаковки, его удаляет антивирус, подробности в README.txt.
  pause
  exit /b 1
)
"%~dp0BallxPit_RU_Font.exe" --uninstall
