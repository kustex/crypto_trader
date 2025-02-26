@echo off
REM Start the X server (VcXsrv) if not already running.
REM Adjust the path below to the correct installation directory on your PC.
start "" "C:\Program Files\VcXsrv\vcxsrv.exe" :0 -multiwindow -ac

REM Give the X server a few seconds to start
timeout /t 3

REM Start the container (if not already running) and execute the GUI module
docker start crypto_app
docker exec -it crypto_app python3 -m app.main

