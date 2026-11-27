@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo [1/3] 检查 Python...
python --version
if errorlevel 1 (
  echo 未找到 python，请先安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)

echo [2/3] 安装依赖...
python -m pip install -r requirements.txt

if not exist "models\classifier.joblib" (
  echo [3/3] 首次运行：生成数据并训练模型...
  python -m src.data_gen --seed 42
  python -m src.train
)

echo 启动网页：http://127.0.0.1:8000
python -m src.webapp --open
pause
