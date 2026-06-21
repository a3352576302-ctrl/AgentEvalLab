#!/usr/bin/env python
"""
scripts/serve.py — 启动 AgentEvalLab API 服务

用法：
    python scripts/serve.py
    python scripts/serve.py --port 8000
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="AgentEvalLab API Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(f"AgentEvalLab API: http://{args.host}:{args.port}")
    print(f"Health check: http://{args.host}:{args.port}/health")
    uvicorn.run("server.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
