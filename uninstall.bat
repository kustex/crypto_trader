@echo off
echo -----------------------------
echo      Uninstall Crypto App
echo -----------------------------
echo.

echo This will DELETE your local database data and remove all Docker containers/images for this app.
set /p AREYOUSURE=Are you sure you want to continue? (y/n):
if /I "%AREYOUSURE%" NEQ "y" (
    echo Uninstall cancelled.
    goto :END
)

echo.
echo Stopping and removing containers...
docker-compose down

echo.
echo Removing Docker volumes...
REM This will remove your postgres_data volume. Ensure this is acceptable.
docker volume rm postgres_data 2>nul

echo.
echo Removing Docker images...
REM Remove the unified app image.
docker rmi smokepaus/crypto_app:latest 2>nul

echo.
echo Removing desktop shortcut...
IF EXIST "%USERPROFILE%\Desktop\Start_Crypto_GUI.bat" (
    del "%USERPROFILE%\Desktop\Start_Crypto_GUI.bat"
)

echo.
echo ✅ Uninstall complete!
echo All containers, images, volumes, and shortcuts have been removed (if they existed).

:END
pause
