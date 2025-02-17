@echo off
echo "🔹 Checking if Docker is installed..."
docker --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo "⚠️ Docker is not installed. Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit /b 1
)

echo "🔹 Pulling latest Docker images..."
docker-compose pull

echo "🔹 Starting backend services (PostgreSQL & data handler)..."
docker-compose up -d

echo "🔹 Creating desktop shortcut for GUI..."
echo [InternetShortcut] > "%USERPROFILE%\Desktop\Start Crypto GUI.url"
echo URL=cmd.exe /C "docker start crypto_gui && docker exec -it crypto_gui python main.py" >> "%USERPROFILE%\Desktop\Start Crypto GUI.url"

echo "✅ Installation complete! Double-click 'Start Crypto GUI' on your desktop to open the app."
exit /b 0
