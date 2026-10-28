from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from extra_setup import extra_status,prepare_extras


class ExtraSetup(unittest.TestCase):
    def test_ready_runtime_does_not_reinstall(self):
        with tempfile.TemporaryDirectory() as tmp,patch('extra_setup.extra_status',return_value=True),patch('extra_setup.subprocess.run') as run:
            prepare_extras(tmp,sys.executable);run.assert_not_called()

    def test_old_runtime_installs_with_registered_python_and_verifies(self):
        with tempfile.TemporaryDirectory(prefix='依赖 空格') as tmp,patch('extra_setup.extra_status',side_effect=[False,True]),patch('extra_setup.subprocess.run',return_value=subprocess.CompletedProcess([],0)) as run:
            prepare_extras(tmp,sys.executable);args=run.call_args.args[0]
            self.assertEqual(args[0],sys.executable);self.assertEqual(args[1:4],['-m','pip','install']);self.assertIn('requirements-extra.txt',args[5]);self.assertTrue((Path(tmp)/'bootstrap.log').exists())

    def test_install_failure_and_failed_probe_are_not_success(self):
        for exit_code in [0,1]:
            with self.subTest(exit_code=exit_code),tempfile.TemporaryDirectory() as tmp,patch('extra_setup.extra_status',return_value=False),patch('extra_setup.subprocess.run',return_value=subprocess.CompletedProcess([],exit_code)):
                with self.assertRaisesRegex(RuntimeError,'安装未完成'):prepare_extras(tmp,sys.executable)

    def test_timeout_and_missing_interpreter_are_not_ready(self):
        self.assertFalse(extra_status(None))
        with patch('extra_setup.subprocess.run',side_effect=subprocess.TimeoutExpired('probe',45)):
            self.assertFalse(extra_status(sys.executable))


if __name__=='__main__':unittest.main()
