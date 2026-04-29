@echo off
:: Устанавливаем кодировку UTF-8 для корректного отображения русского языка
chcp 65001 > nul
setlocal
title PCAR Brain Loader (NiceGUI)

color 0A

echo ======================================================
echo          PCAR: ПЕРСОНАЛЬНЫЙ ЦИФРОВОЙ МОЗГ
echo ======================================================

:: Переходим в папку скрипта
cd /d "%~dp0"

:: Проверяем наличие Python в виртуальном окружении .venv
:: Мы используем .venv (с точкой), так как это стандарт для VS Code
set VENV_PYTHON="%~dp0.venv\Scripts\python.exe"

if not exist %VENV_PYTHON% (
    color 0C
    echo [ERROR] Виртуальное окружение .venv не найдено в папке проекта!
    echo [FIX] Попробуй создать его командой: python -m venv .venv
    pause
    exit /b
)

echo [SYSTEM] Проверка библиотек внутри .venv...
:: Используем -m pip, чтобы избежать ошибок "Fatal error in launcher"
%VENV_PYTHON% -m pip install nicegui pandas plotly requests python-dotenv chromadb sentence-transformers transitions html-sanitizer >nul 2>&1

if %ERRORLEVEL% neq 0 (
    echo [WARN] Некоторые зависимости не установлены. Запускаю принудительное обновление...
    %VENV_PYTHON% -m pip install nicegui pandas plotly requests python-dotenv chromadb sentence-transformers transitions html-sanitizer
)

echo [SYSTEM] Запуск сервера (порт 8080)...
echo ------------------------------------------------------

:: Запуск основного файла [cite: 852]
%VENV_PYTHON% src\main.py

if %ERRORLEVEL% neq 0 (
    color 0C
    echo.
    echo [CRITICAL] Ошибка при запуске. Проверь логи выше.
    pause
)