import argparse
import uvicorn

from .main import create_app

parser = argparse.ArgumentParser(description='Local offline analyst API')
parser.add_argument('--port', type=int, default=18105)
args = parser.parse_args()
uvicorn.run(create_app(), host='127.0.0.1', port=args.port)
