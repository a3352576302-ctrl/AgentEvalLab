FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目（.env 通过 docker-compose 注入，不打包进镜像）
COPY . .

# 默认命令：rule 模式 smoke run
CMD ["python", "scripts/run_report.py", "--html-only", "--save-run", "--run-id", "docker-demo"]
