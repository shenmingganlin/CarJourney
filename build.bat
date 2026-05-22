@echo off
chcp 65001
echo 正在检查 PyInstaller...
pip install pyinstaller
echo.
echo 开始打包，请稍候...
pyinstaller --onefile --windowed --icon=icon.ico --name=CarJourney --add-data=game/assets;game/assets --add-data=icon.png;. main.py
echo.
echo 完成！请检查 dist 文件夹
pause
