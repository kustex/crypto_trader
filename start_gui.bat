@echo off
docker start crypto_gui
docker exec -it crypto_gui python main.py
