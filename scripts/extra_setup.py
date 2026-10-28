"""Verify and repair this Skill's extra dependencies in the registered runtime."""
from pathlib import Path
import subprocess
import sys

REQUIREMENTS=Path(__file__).resolve().parents[1]/'assets/requirements-extra.txt'
PROBE="""from importlib.metadata import version
from pathlib import Path
from packaging.requirements import Requirement
import sys
for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line or line.startswith('#'):continue
    item=Requirement(line)
    if item.marker and not item.marker.evaluate():continue
    assert item.specifier.contains(version(item.name),prereleases=True),item.name
import pypdfium2
document=pypdfium2.PdfDocument.new()
document.close()
"""


def extra_status(python):
    if not python or not Path(python).is_file():return False
    try:
        result=subprocess.run([str(python),'-c',PROBE,str(REQUIREMENTS)],capture_output=True,timeout=45,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.returncode==0
    except (OSError,subprocess.TimeoutExpired):return False


def prepare_extras(root,python):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if extra_status(python):return
    log=root/'bootstrap.log'
    print('补装文案工坊依赖（含 PDF 解析）；日志：'+str(log),file=sys.stderr,flush=True)
    constraints=root/'studio-extra-constraints.txt';constraints.write_text('numpy<2.3\n',encoding='ascii')
    try:
        with log.open('a',encoding='utf-8') as output:
            result=subprocess.run([str(python),'-m','pip','install','-r',str(REQUIREMENTS),'-c',str(constraints)],
                stdout=output,stderr=output,timeout=900,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode or not extra_status(python):raise RuntimeError('文案工坊新增依赖未就绪，安装未完成。请查看 bootstrap.log，修复网络后重跑安装。')
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise RuntimeError('文案工坊依赖安装失败或超时，安装未完成。请查看 bootstrap.log 后重试。') from exc
