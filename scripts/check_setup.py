import json
from app.diagnostics import setup_status

if __name__ == '__main__':
    print(json.dumps(setup_status(), indent=2))
