Crypto Trading App - Installation Instructions
-----------------------------------------------
1. Prerequisites:
   - Your PC must have Docker Desktop installed.
     If you do not have Docker Desktop, download and install it from:
     https://www.docker.com/products/docker-desktop
   - Ensure Docker Desktop is running (you should see the Docker whale icon in your system tray).
   - On Windows, you must also have an X server (e.g., VcXsrv or Xming) installed and running 
     to display the GUI. If you don't have one, download and install VcXsrv from:
     https://sourceforge.net/projects/vcxsrv/

2. Unzip the Package:
   - Unzip the "Crypto_Trading_App.zip" folder to your desired location on your PC.

3. Install the Application:
   - Open the unzipped folder.
   - Run "install.bat" by double-clicking it.
     This batch script will:
       • Check that Docker Desktop is installed.
       • Pull the latest Docker images from the registry.
       • Start the PostgreSQL and application containers using docker-compose.
       • Create a desktop shortcut (Start_Crypto_GUI.bat) to launch the GUI on demand.
   - Follow any prompts in the command window.

4. Launch the GUI:
   - After "install.bat" completes, a shortcut file named "Start_Crypto_GUI.bat" will be created on your Desktop.
   - Double-click "Start_Crypto_GUI.bat" to launch the GUI.
     (If you encounter any errors, the window will remain open so you can read the error messages.)

5. Uninstallation (Optional):
   - If you need to uninstall the application, run "uninstall.bat" from the unzipped folder.
     This will:
       • Stop and remove Docker containers.
       • Remove the local database volume.
       • Remove the application images.
       • Delete the desktop shortcut.

-----------------------------------------------
Important Notes:
   • Docker commands require Docker Desktop to be running. If Docker Desktop is not running,
     the batch scripts will not work.
   • Make sure your X server (e.g., VcXsrv) is running before launching the GUI.
   • For any issues, check the console output for error messages.
-----------------------------------------------
