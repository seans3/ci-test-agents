import unittest
from unittest.mock import patch, MagicMock
import json
import extract_metrics

class TestExtractMetrics(unittest.TestCase):

    @patch('extract_metrics.subprocess.run')
    def test_find_and_fetch_gcs_json_success(self, mock_run):
        # Setup mock responses for ls and cat
        mock_ls = MagicMock()
        mock_ls.stdout = "gs://bucket/APIResponsivenessPrometheus_load_123Z.json\n"
        
        mock_cat = MagicMock()
        mock_cat.stdout = '{"key": "value"}'
        
        mock_run.side_effect = [mock_ls, mock_cat]
        
        result = extract_metrics.find_and_fetch_gcs_json("12345", "APIResponsivenessPrometheus_load")
        
        self.assertEqual(result, {"key": "value"})
        self.assertEqual(mock_run.call_count, 2)

    @patch('extract_metrics.subprocess.run')
    def test_find_and_fetch_gcs_json_skips_simple(self, mock_run):
        # Setup mock responses where the first match has 'simple' in the name
        mock_ls = MagicMock()
        mock_ls.stdout = "gs://bucket/APIResponsivenessPrometheus_load_simple.json\ngs://bucket/APIResponsivenessPrometheus_load_123Z.json\n"
        
        mock_cat = MagicMock()
        mock_cat.stdout = '{"key": "value"}'
        
        mock_run.side_effect = [mock_ls, mock_cat]
        
        result = extract_metrics.find_and_fetch_gcs_json("12345", "APIResponsivenessPrometheus_load")
        
        # Verify it still extracts successfully by picking the non-simple file
        self.assertEqual(result, {"key": "value"})
        self.assertEqual(mock_run.call_count, 2)

    @patch('extract_metrics.subprocess.run')
    def test_find_and_fetch_gcs_json_not_found(self, mock_run):
        # Simulate a grep failure (file not found)
        mock_run.side_effect = extract_metrics.subprocess.CalledProcessError(1, "cmd")
        
        result = extract_metrics.find_and_fetch_gcs_json("12345", "prefix")
        self.assertEqual(result, {})

    def test_extract_api_count_success(self):
        data = {
            "dataItems": [
                {
                    "labels": {
                        "Resource": "pods",
                        "Scope": "cluster",
                        "Verb": "LIST",
                        "Count": "581"
                    }
                }
            ]
        }
        count = extract_metrics.extract_api_count(data)
        self.assertEqual(count, 581)

    def test_extract_api_count_fallback(self):
        data = {"metric": "Something else entirely"}
        count = extract_metrics.extract_api_count(data)
        self.assertEqual(count, 400)

    def test_extract_api_count_empty(self):
        count = extract_metrics.extract_api_count({})
        self.assertEqual(count, 400)

    def test_build_metrics_payload(self):
        payload = extract_metrics.build_metrics_payload("fail_123", "base_456", 500, 300)
        
        # Assert metadata
        self.assertEqual(payload["metadata"]["failed_build_id"], "fail_123")
        self.assertEqual(payload["metadata"]["baseline_build_id"], "base_456")
        
        # Assert time series scaling logic
        # 500 * 6.1 = 3050.0
        self.assertEqual(payload["time_series_data"][1]["failed_run"]["concurrency_inflight"], 3050.0)
        self.assertEqual(payload["time_series_data"][1]["baseline_run"]["concurrency_inflight"], 300)
        
        # Assert static values
        self.assertEqual(payload["hardware_limits"]["kube_apiserver_memory_limit_gb"], 64.0)

if __name__ == '__main__':
    unittest.main()