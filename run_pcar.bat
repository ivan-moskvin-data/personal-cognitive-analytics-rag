@echo off
:: Устанавливаем кодировку UTF-8 для корректного отображения русского языка
chcp 65001 > nul
setlocal
title PCAR Brain Loader

color 0A

echo ======================================================
echo          PCAR: ПЕРСОНАЛЬНЫЙ ЦИФРОВОЙ МОЗГ
echo ======================================================

:: Переходим в папку скрипта
cd /d "%~dp0"

:: Проверяем наличие Python в виртуальном окружении
set VENV_PYTHON="%~dp0venv\Scripts\python.exe"

if not exist %VENV_PYTHON% (
    color 0C
    echo [ERROR] Файл %VENV_PYTHON% не найден!
    echo [FIX] Похоже, venv не создана или создана неправильно.
    pause
    exit /b
)

echo [SYSTEM] Проверка библиотек...
:: Пробуем запустить streamlit через прямой путь. 
:: Если не выйдет - попробуем его доустановить прямо сейчас.
%VENV_PYTHON% -m streamlit --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [WARN] Streamlit не найден внутри venv. Пытаюсь установить...
    %VENV_PYTHON% -m pip install streamlit pandas plotly requests python-dotenv chromadb sentence-transformers transitions
)

echo [SYSTEM] Запуск сервера...
echo ------------------------------------------------------

:: Запуск через прямой путь к Python из venv
%VENV_PYTHON% -m streamlit run src\app.py --theme.base="dark"

if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo [CRITICAL] Ошибка при запуске. Проверь логи выше.
    pause
)