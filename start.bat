@echo off
chcp 65001 >nul
set P=E:\wh\10nodata\program\chatex
start llama cmd /c "%%P%%\llama\llama-server.exe -m %%P%%\models\qwen3-5-2B-Q4_K_M.gguf --host 127.0.0.1 --port 8848 --ctx-size 8192 --threads 8 --n-predict -1 --cache-type-k q8_0 --cache-type-v q8_0 --log-disable -ngl 35"
timeout /t 5 /nobreak >nul
start api cmd /c "%%P%%\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 9090 --log-level info"
echo Ready: http://127.0.0.1:9090
pause
