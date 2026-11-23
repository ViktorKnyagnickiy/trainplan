@echo off
rem TrainPlan: start the local server and open the browser
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
start "" cmd /c "timeout /t 3 /nobreak >/dev/null & start http://127.0.0.1:5000"
echo TrainPlan is running at http://127.0.0.1:5000
echo Close this window to stop the server.
python app.py
pause
