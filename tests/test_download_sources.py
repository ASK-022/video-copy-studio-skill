from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_sources import pip_install,PIP_INDEXES
from bootstrap import upstream,UPSTREAM_SHA256


class DownloadSources(unittest.TestCase):
    def test_primary_failure_switches_index_without_mixing_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('download_sources.subprocess.run',side_effect=[subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0)]) as run:
                label=pip_install(sys.executable,['rapidfuzz==3.14.0'],Path(folder)/'bootstrap.log')
            self.assertEqual(label,PIP_INDEXES[1][0]);self.assertEqual(run.call_count,2)
            for call,(_,index) in zip(run.call_args_list,PIP_INDEXES):
                command=call.args[0]
                self.assertEqual(command[0],sys.executable)
                self.assertEqual(command.count('--index-url'),1)
                self.assertEqual(command[command.index('--index-url')+1],index)
                self.assertNotIn('--extra-index-url',command)
                self.assertNotIn('--trusted-host',command)
                self.assertEqual(call.kwargs['env']['PIP_EXTRA_INDEX_URL'],'')

    def test_timeout_falls_back_but_all_failures_are_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('download_sources.subprocess.run',side_effect=subprocess.TimeoutExpired('pip',1)) as run:
                with self.assertRaisesRegex(RuntimeError,'安装未完成'):pip_install(sys.executable,['pip'],Path(folder)/'bootstrap.log')
            self.assertEqual(run.call_count,len(PIP_INDEXES))

    def test_success_does_not_contact_remaining_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('download_sources.subprocess.run',return_value=subprocess.CompletedProcess([],0)) as run:
                pip_install(sys.executable,['pip'],Path(folder)/'bootstrap.log')
            self.assertEqual(run.call_count,1)

    def test_bundled_runtime_is_verified_and_installed_without_github(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'runtime'
            with patch('bootstrap.download',side_effect=AssertionError('Network must not be used')):
                upstream(target)
            self.assertEqual((target/'.studio-upstream-revision').read_text(),UPSTREAM_SHA256)
            self.assertIn('async with self.model_lock:',(target/'core/sensevoice_transcriber.py').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
