"""Run browser import outside the web server's Windows asyncio event-loop policy."""
from pathlib import Path
import sys

from client.media import public_douyin

if __name__=='__main__':
    try:
        result=public_douyin(sys.argv[1],Path(sys.argv[2]),lambda message:print(message,flush=True))
        print('Public media with audio downloaded.',flush=True)
    except Exception as exc:
        # No cookies, credentials or signed media URLs in diagnostics.
        print('Browser import failed: '+type(exc).__name__,file=sys.stderr,flush=True)
        raise SystemExit(1)
