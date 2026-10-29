import json
from pathlib import Path
import tempfile
import unittest
from client.workspace import identity


class WorkspaceIdentity(unittest.TestCase):
    def test_identity_belongs_to_data_and_survives_source_updates(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            value = identity(first)
            self.assertEqual(identity(Path(first)), value)
            self.assertNotEqual(identity(second), value)
            manifest = json.loads((Path(first)/'content-hub-workspace.json').read_text())
            self.assertEqual(manifest['id'], value)

    def test_invalid_manifest_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as state:
            path = Path(state)/'content-hub-workspace.json'
            path.write_text('{"schema":"wrong","id":"invalid"}')
            with self.assertRaises(ValueError):identity(state)
            self.assertIn('wrong',path.read_text())
