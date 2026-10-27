"""Copy this skill into an Agent's skill directory; updates retain a backup."""
import argparse
import sys
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil

NAME='video-copy-studio'


def install(source,skills_dir,update=False):
    source=Path(source).resolve();root=Path(skills_dir).expanduser().resolve();target=root/NAME
    if not (source/'SKILL.md').is_file():raise ValueError('源目录不是完整 Skill。')
    if source==target:return {'installed_path':str(target),'already_here':True}
    if target.is_symlink():raise ValueError('目标是符号链接，请选择实际的技能目录。')
    if target.exists() and not update:raise ValueError('同名 Skill 已存在；确认升级时指定 --update。')
    if source.is_relative_to(target) or target.is_relative_to(source):raise ValueError('源目录与安装目录不能互相包含。')
    root.mkdir(parents=True,exist_ok=True)
    staging=root/(NAME+'.installing-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
    if not staging.resolve().is_relative_to(root) or not target.resolve().is_relative_to(root):raise ValueError('安装路径越界。')
    shutil.copytree(source,staging,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','*.pyc','node_modules','.studio','dist'))
    backup=None
    if target.exists():
        backup=root/(NAME+'.backup-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
        if not backup.resolve().is_relative_to(root):raise ValueError('备份路径越界。')
        target.rename(backup)
    try:staging.rename(target)
    except Exception:
        if backup and not target.exists():backup.rename(target)
        raise
    return {'installed_path':str(target),'backup_path':str(backup) if backup else None,'restart_agent_or_start_new_chat':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent',choices=['codex','claude','openclaw','custom'],default='codex')
    parser.add_argument('--skills-dir',type=Path);parser.add_argument('--update',action='store_true')
    args=parser.parse_args()
    roots={'codex':Path.home()/'.codex/skills','claude':Path.home()/'.claude/skills','openclaw':Path.home()/'.openclaw/skills'}
    if args.agent=='custom' and not args.skills_dir:raise ValueError('custom 需要 --skills-dir。')
    print(json.dumps(install(Path(__file__).resolve().parents[1],args.skills_dir or roots[args.agent],args.update),ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
