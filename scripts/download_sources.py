"""Per-command HTTPS mirrors with bounded retries; never changes global pip settings."""
import os
from pathlib import Path
import subprocess
import sys

PIP_INDEXES=(
    ('清华镜像','https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'),
    ('华为镜像','https://repo.huaweicloud.com/repository/pypi/simple'),
    ('PyPI 官方','https://pypi.org/simple'),
)
BROWSER_HOSTS=(
    ('npmmirror 浏览器镜像','https://cdn.npmmirror.com/binaries/playwright'),
    ('Playwright 官方',None),
)


def pip_install(python,arguments,log,timeout=1200,indexes=None):
    """Use one index at a time, switching on error or timeout with the same Python."""
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    for label,index in (PIP_INDEXES if indexes is None else indexes):
        message='安装依赖：'+label
        print(message+'；日志：'+str(log),file=sys.stderr,flush=True)
        env=dict(os.environ,PYTHONIOENCODING='utf-8',PIP_CONFIG_FILE=os.devnull,PIP_EXTRA_INDEX_URL='',PIP_USER='false')
        command=[str(python),'-m','pip','install',*map(str,arguments),'--index-url',index,
                 '--disable-pip-version-check','--no-input','--timeout','20','--retries','1']
        with log.open('a',encoding='utf-8') as output:
            output.write('\n'+message+'\n');output.flush()
            try:
                result=subprocess.run(command,env=env,stdout=output,stderr=output,timeout=timeout,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode==0:return label
            except (OSError,subprocess.TimeoutExpired) as exc:
                output.write('\n下载尝试失败：'+type(exc).__name__+'\n')
            output.write('当前源未完成安装，自动切换下一下载源。\n')
    raise RuntimeError('所有依赖下载源均未完成安装，安装未完成。请查看 '+str(log)+'，修复网络后重试。')
