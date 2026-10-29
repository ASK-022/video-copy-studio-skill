"""A data workspace keeps its identity when the Skill's source directory changes."""
import json
from pathlib import Path
import threading
import uuid

CAPABILITIES = ['resume', 'script-preview', 'text-review', 'editorial', 'library-metadata', 'manuscript-handoff']
_lock = threading.Lock()


def identity(state):
    path = Path(state) / 'content-hub-workspace.json'
    with _lock:
        try:
            with path.open('x', encoding='utf-8') as stream:
                value = {'schema': 'content-hub/workspace/v1', 'id': str(uuid.uuid4())}
                json.dump(value, stream, ensure_ascii=False, indent=2)
        except FileExistsError:
            value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema') != 'content-hub/workspace/v1' or str(uuid.UUID(value['id'])) != value['id']:
            raise ValueError('内容中台工作区标识无效，请核对资料目录。')
        return value['id']
