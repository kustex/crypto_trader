@echo off
echo "🔹 Checking if Docker is installed..."
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo "⚠️ Docker is not installed. Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit /b 1
)

echo "🔹 Pulling latest Docker images..."
docker-compose pull

echo "🔹 Starting services (PostgreSQL & data handler)..."
docker-compose up -d

REM Create a .bat file on the desktop that starts the GUI on demand
echo "🔹 Creating desktop shortcut for GUI..."
(
    echo @echo off
    echo docker start crypto_app
    echo docker exec -it crypto_app python -m app.main
) > "%USERPROFILE%\Desktop\Start_Crypto_GUI.bat"

echo "✅ Installation complete! Double-click 'Start_Crypto_GUI.bat' on your desktop to open the GUI."
exit /b 0
