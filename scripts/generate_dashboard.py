"""
5k-Node Performance Test Visualization Generator

This script parses a normalized JSON matrix containing temporal telemetry from 
a Kubernetes 5k-node scalability test and generates a multi-panel "Trellis Layout"
dashboard of .png graphs.

The visualizations are designed to bridge subsystem silos, correlating traffic surges 
(Concurrency) with hardware saturation (CPU, Memory, Disk) across a synchronized 
time axis (T-5m to T+5m).
"""

import argparse
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

def load_data(filepath):
    """Loads the normalized JSON matrix."""
    with open(filepath, 'r') as f:
        return json.load(f)

def setup_plotting():
    """Configures global plotting aesthetics using seaborn."""
    sns.set_theme(style="darkgrid")
    plt.rcParams['figure.figsize'] = (10, 6)
    plt.rcParams['figure.dpi'] = 150

def generate_concurrency_plot(data, output_dir):
    """
    Dimension 1: Concurrency Surge
    
    Generates a dual-axis line chart overlaying the failed run's inflight requests 
    against the baseline (LKG) run's inflight requests. 
    This visually proves "Thundering Herd" anomalies.
    """
    time_series = data.get("time_series_data", [])
    if not time_series:
        print("No time series data found.")
        return

    times = [tick["relative_time_seconds"] for tick in time_series]
    failed_inflight = [tick["failed_run"].get("concurrency_inflight", 0) for tick in time_series]
    baseline_inflight = [tick.get("baseline_run", {}).get("concurrency_inflight", 0) for tick in time_series]
    apf_queued = [tick["failed_run"].get("apf_queued", 0) for tick in time_series]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Plot baseline ghost overlay (dashed gray) to prove the mathematical anomaly
    if any(baseline_inflight):
        ax1.plot(times, baseline_inflight, color='gray', linestyle='--', label='Baseline Inflight (LKG)')
    
    # Plot the actual traffic surge
    ax1.plot(times, failed_inflight, color='crimson', linewidth=2, label='Failed Run Inflight')
    
    ax1.set_xlabel('Relative Time (seconds from failure)')
    ax1.set_ylabel('Inflight Requests', color='black')
    
    # Anchor the graph around T=0 (The SLO Breach / Failure Event)
    ax1.axvline(0, color='black', linestyle=':', label='T=0 (Failure Event)')

    # If APF queues are backing up, plot them on a secondary Y-axis
    if any(apf_queued):
        ax2 = ax1.twinx()
        ax2.plot(times, apf_queued, color='blue', linewidth=2, label='APF Queued')
        ax2.set_ylabel('APF Queued Requests', color='blue')
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc='upper left')
    else:
        ax1.legend(loc='upper left')

    plt.title('Dimension 1: Concurrency Surge\n(Did traffic exceed expected bounds?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim1_concurrency.png'))
    plt.close()

def generate_cpu_plot(data, output_dir):
    """
    Dimension 2: API Server CPU Saturation
    
    Generates a stacked area chart separating Garbage Collection (GC) CPU cores 
    from Core Logic cores. This explicitly proves whether the API server choked 
    on memory allocation (GC) or business logic (Locks/Serialization).
    """
    time_series = data.get("time_series_data", [])
    times = [tick["relative_time_seconds"] for tick in time_series]
    
    total_cpu = np.array([tick["failed_run"].get("cpu_total_cores", 0) for tick in time_series])
    gc_cpu = np.array([tick["failed_run"].get("cpu_gc_cores", 0) for tick in time_series])
    baseline_cpu = np.array([tick.get("baseline_run", {}).get("cpu_total_cores", 0) for tick in time_series])
    
    # Subtract GC overhead to find the remaining CPU utilized by core logic
    non_gc_cpu = total_cpu - gc_cpu
    non_gc_cpu = np.maximum(non_gc_cpu, 0) # Ensure no negative plotting artifacts

    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Stack the GC (red) underneath Core Logic (blue)
    ax.stackplot(times, gc_cpu, non_gc_cpu, labels=['Garbage Collection Overhead', 'Core Logic / Lock Contention'], colors=['salmon', 'steelblue'], alpha=0.8)
    
    # Overlay the baseline to show what healthy CPU usage looks like
    if any(baseline_cpu):
        ax.plot(times, baseline_cpu, color='gray', linestyle='--', linewidth=2, label='Baseline Total CPU (Healthy)')
        
    ax.axvline(0, color='black', linestyle=':', linewidth=2, label='T=0 (Traffic Spike)')

    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('CPU Cores')
    ax.set_ylim(0, 64) # Hardcoded to max cores of typical monolithic control plane
    
    ax.legend(loc='upper left', frameon=True, shadow=True, title="CPU Consumption Breakdown")
    
    plt.title('Dimension 2: API Server CPU Saturation\n(What was the CPU doing when it locked up?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim2_cpu.png'))
    plt.close()

def generate_pprof_pie(data, output_dir):
    """
    Dimension 3: Static Profiling (T=0)
    
    Generates a Pie Chart representing the `.pprof` CPU profile snapshot taken 
    exactly at T=0. This isolates the specific Go function locking the system.
    """
    pprof = data.get("pprof_snapshot_t_zero")
    if not pprof:
        print("No pprof snapshot data found.")
        return

    labels = []
    sizes = []
    for key, value in pprof.items():
        labels.append(key.replace('_cpu_percent', ''))
        sizes.append(value)
    
    # Aggregate remaining percentages into 'other'
    total_accounted = sum(sizes)
    if total_accounted < 100:
        labels.append('other')
        sizes.append(100 - total_accounted)

    fig, ax = plt.subplots()
    
    # Visually emphasize (explode) the largest bottleneck
    explode = [0.1 if s == max(sizes) else 0 for s in sizes]
    
    ax.pie(sizes, explode=explode, labels=labels, autopct='%1.1f%%', shadow=True, startangle=90)
    ax.axis('equal')
    plt.title('Dimension 3: pprof CPU Profile Snapshot at T=0\n(Which specific function blocked execution?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim3_pprof_pie.png'))
    plt.close()

def generate_memory_plot(data, output_dir):
    """
    Dimension 4: Memory Exhaustion
    
    Plots the working set memory against the container's hard cgroup limit 
    to visually prove or disprove OOM kills.
    """
    time_series = data.get("time_series_data", [])
    times = [tick["relative_time_seconds"] for tick in time_series]
    mem_usage = [tick["failed_run"].get("memory_working_set_gb", 0) for tick in time_series]
    
    # Fetch the hardware limit from the metadata payload
    limit_gb = data.get("hardware_limits", {}).get("kube_apiserver_memory_limit_gb")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, mem_usage, color='purple', linewidth=2, label='Memory Working Set (GB)')
    
    # Draw the critical threshold ceiling
    if limit_gb:
        ax.axhline(limit_gb, color='red', linestyle='dashed', linewidth=2, label=f'CGroup Limit ({limit_gb}GB)')
        ax.set_ylim(0, limit_gb * 1.1)

    ax.axvline(0, color='black', linestyle=':', label='T=0')
    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('Memory (GB)')
    ax.legend(loc='upper left')
    plt.title('Dimension 4: Memory Exhaustion\n(Did the node run out of RAM?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim4_memory.png'))
    plt.close()

def generate_etcd_plot(data, output_dir):
    """
    Dimension 5: Etcd Disk IOPS (P99)
    
    Plots the 99th percentile fsync duration for etcd against a critical 50ms 
    threshold to visually exonerate or implicate the underlying cloud storage layer.
    """
    time_series = data.get("time_series_data", [])
    if not time_series:
        return
        
    times = [tick["relative_time_seconds"] for tick in time_series]
    failed_p99 = [tick["failed_run"].get("etcd_fsync_p99_ms", 0) for tick in time_series]
    baseline_p99 = [tick.get("baseline_run", {}).get("etcd_fsync_p99_ms", 0) for tick in time_series]

    fig, ax = plt.subplots(figsize=(10, 6))
    
    if any(baseline_p99):
        ax.plot(times, baseline_p99, color='gray', linestyle='--', linewidth=2, label='Baseline P99 (Healthy)')
        
    ax.plot(times, failed_p99, color='crimson', linewidth=2, label='Failed Run P99')
    
    # The Etcd Critical Warning Threshold (Disks > 50ms cause cluster instability)
    ax.axhline(50, color='red', linestyle='dashed', linewidth=2, label='50ms Critical Threshold')
    
    # Dynamically scale Y-axis to ensure the 50ms line is always visible
    max_val = max(max(failed_p99), max(baseline_p99) if baseline_p99 else 0)
    ax.set_ylim(0, max(60, max_val * 1.1))

    ax.axvline(0, color='black', linestyle=':', label='T=0 (Traffic Spike)')
    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('Fsync Latency (ms)')
    ax.legend(loc='upper left', frameon=True, shadow=True)
    plt.title('Dimension 5: Etcd Disk IOPS (P99 Latency)\n(Did the storage layer bottleneck?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim5_etcd_p99.png'))
    plt.close()

def main():
    parser = argparse.ArgumentParser(description="Generate 5k-node performance visualizations from JSON matrix.")
    parser.add_argument("input_json", help="Path to the normalized JSON matrix.")
    parser.add_argument("output_dir", help="Directory to save the generated graphs.")
    
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    data = load_data(args.input_json)
    
    setup_plotting()
    
    generate_concurrency_plot(data, args.output_dir)
    generate_cpu_plot(data, args.output_dir)
    generate_pprof_pie(data, args.output_dir)
    generate_memory_plot(data, args.output_dir)
    generate_etcd_plot(data, args.output_dir)
    
    print(f"Visualizations successfully generated in: {args.output_dir}")

if __name__ == "__main__":
    main()