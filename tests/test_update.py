import json
import unittest
from unittest.mock import Mock, patch
from src.services import resolve_connection as connection
from src.tools import analysis


class ConnectionTests(unittest.TestCase):
    def tearDown(self):
        connection._resolve = None

    def test_stale_handle_reconnects(self):
        stale = Mock()
        stale.GetProductName.return_value = None
        fresh = Mock()
        fresh.GetProductName.return_value = "DaVinci Resolve Studio"
        connection._resolve = stale
        with patch.dict("sys.modules", {"DaVinciResolveScript": Mock(scriptapp=Mock(return_value=fresh))}):
            self.assertIs(connection.get_resolve(), fresh)

    def test_failed_import_reports_diagnostic(self):
        connection._resolve = None
        with patch.dict("sys.modules", {"DaVinciResolveScript": None}):
            with self.assertRaisesRegex(RuntimeError, "Scripting modules:"):
                connection.get_resolve()


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.resolve = Mock()
        self.resolve.GetVersion.return_value = [21, 0, 4, 5]
        self.folder = Mock()
        self.folder.GetName.return_value = "Interviews"
        self.pool = Mock()
        self.pool.GetCurrentFolder.return_value = self.folder
        p = patch.object(analysis, "get_resolve", return_value=self.resolve)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(analysis, "get_media_pool", return_value=self.pool)
        p.start()
        self.addCleanup(p.stop)

    def test_older_resolve_rejected_before_operation(self):
        self.resolve.GetVersion.return_value = [20, 3]
        with self.assertRaisesRegex(RuntimeError, "21"):
            analysis._run("TranscribeAudio", "", True)
        self.folder.TranscribeAudio.assert_not_called()

    def test_duplicate_names_rejected_before_operation(self):
        clip = Mock()
        clip.GetName.return_value = "Interview"
        self.folder.GetClipList.return_value = [clip, clip]
        with self.assertRaisesRegex(ValueError, "found 2"):
            analysis._run("TranscribeAudio", "Interview", False)
        clip.TranscribeAudio.assert_not_called()

    def test_speaker_flag_passed_to_folder(self):
        self.folder.TranscribeAudio.return_value = True
        result = json.loads(analysis._run("TranscribeAudio", "", True))
        self.assertTrue(result["success"])
        self.folder.TranscribeAudio.assert_called_once_with(True)

    def test_native_failure_not_reported_as_success(self):
        self.folder.PerformAudioClassification.return_value = False
        self.assertFalse(json.loads(analysis._run("PerformAudioClassification", ""))["success"])


if __name__ == "__main__":
    unittest.main()
