#!/usr/bin/env python3
import json
import subprocess

bucket = "gs://kubernetes-ci-logs/logs/ci-kubernetes-e2e-gce-scale-performance-5000"

def get_duration(build_id):
    try:
        start_cmd = f"gcloud storage cat {bucket}/{build_id}/started.json"
        end_cmd = f"gcloud storage cat {bucket}/{build_id}/finished.json"
        
        start_res = subprocess.run(start_cmd, shell=True, capture_output=True, text=True)
        end_res = subprocess.run(end_cmd, shell=True, capture_output=True, text=True)
        
        start_data = json.loads(start_res.stdout)
        end_data = json.loads(end_res.stdout)
        
        start_ts = start_data.get("timestamp")
        end_ts = end_data.get("timestamp")
        
        if start_ts and end_ts:
            minutes = (end_ts - start_ts) / 60
            return minutes
    except Exception as e:
        pass
    return None

failures = ["2067291549904932864", "2066566728590036992", "2058231898483724288"]
successes = ["2063667733328826368", "2062942951578800128", "2057507115173416960"]

print("=== Failures ===")
for b in failures:
    print(f"{b}: {get_duration(b)} minutes")

print("=== Successes ===")
for b in successes:
    print(f"{b}: {get_duration(b)} minutes")
