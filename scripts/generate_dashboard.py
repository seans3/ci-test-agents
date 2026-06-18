import argparse
import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

def load_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def setup_plotting():
    sns.set_theme(style="darkgrid")
    plt.rcParams['figure.figsize'] = (10, 6)
    plt.rcParams['figure.dpi'] = 150

def generate_concurrency_plot(data, output_dir):
    time_series = data.get("time_series_data", [])
    if not time_series:
        print("No time series data found.")
        return

    times = [tick["relative_time_seconds"] for tick in time_series]
    failed_inflight = [tick["failed_run"].get("concurrency_inflight", 0) for tick in time_series]
    baseline_inflight = [tick.get("baseline_run", {}).get("concurrency_inflight", 0) for tick in time_series]
    apf_queued = [tick["failed_run"].get("apf_queued", 0) for tick in time_series]

    fig, ax1 = plt.subplots()
    
    # Plot baseline ghost
    if any(baseline_inflight):
        ax1.plot(times, baseline_inflight, color='gray', linestyle='--', label='Baseline Inflight (LKG)')
    
    # Plot failed run
    ax1.plot(times, failed_inflight, color='crimson', linewidth=2, label='Failed Run Inflight')
    
    ax1.set_xlabel('Relative Time (seconds from failure)')
    ax1.set_ylabel('Inflight Requests', color='black')
    ax1.axvline(0, color='black', linestyle=':', label='T=0 (Failure Event)')

    # APF Queued on secondary axis
    if any(apf_queued):
        ax2 = ax1.twinx()
        ax2.plot(times, apf_queued, color='blue', linewidth=2, label='APF Queued')
        ax2.set_ylabel('APF Queued Requests', color='blue')
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc='upper left')
    else:
        ax1.legend(loc='upper left')

    plt.title('Dimension 1: Concurrency Surge')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim1_concurrency.png'))
    plt.close()

def generate_cpu_plot(data, output_dir):
    time_series = data.get("time_series_data", [])
    times = [tick["relative_time_seconds"] for tick in time_series]
    
    total_cpu = np.array([tick["failed_run"].get("cpu_total_cores", 0) for tick in time_series])
    gc_cpu = np.array([tick["failed_run"].get("cpu_gc_cores", 0) for tick in time_series])
    baseline_cpu = np.array([tick.get("baseline_run", {}).get("cpu_total_cores", 0) for tick in time_series])
    
    # Calculate non-GC CPU for the stack
    non_gc_cpu = total_cpu - gc_cpu
    non_gc_cpu = np.maximum(non_gc_cpu, 0) # ensure no negatives

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.stackplot(times, gc_cpu, non_gc_cpu, labels=['Garbage Collection Overhead', 'Core Logic / Lock Contention'], colors=['salmon', 'steelblue'], alpha=0.8)
    
    if any(baseline_cpu):
        ax.plot(times, baseline_cpu, color='gray', linestyle='--', linewidth=2, label='Baseline Total CPU (Healthy)')
        
    ax.axvline(0, color='black', linestyle=':', linewidth=2, label='T=0 (Traffic Spike)')

    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('CPU Cores')
    ax.set_ylim(0, 64) # Max cores
    
    # Place legend (the 'table' box) outside the plot if it's blocking data, or keep it upper left with a frame
    ax.legend(loc='upper left', frameon=True, shadow=True, title="CPU Consumption Breakdown")
    
    plt.title('Dimension 2: API Server CPU Saturation\n(What was the CPU doing when it locked up?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim2_cpu.png'))
    plt.close()

def generate_pprof_pie(data, output_dir):
    pprof = data.get("pprof_snapshot_t_zero")
    if not pprof:
        print("No pprof snapshot data found.")
        return

    labels = []
    sizes = []
    for key, value in pprof.items():
        labels.append(key.replace('_cpu_percent', ''))
        sizes.append(value)
    
    # Calculate 'Other'
    total_accounted = sum(sizes)
    if total_accounted < 100:
        labels.append('other')
        sizes.append(100 - total_accounted)

    fig, ax = plt.subplots()
    # Pull the largest slice out slightly
    explode = [0.1 if s == max(sizes) else 0 for s in sizes]
    
    ax.pie(sizes, explode=explode, labels=labels, autopct='%1.1f%%', shadow=True, startangle=90)
    ax.axis('equal')
    plt.title('Dimension 3: pprof CPU Profile Snapshot at T=0')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim3_pprof_pie.png'))
    plt.close()

def generate_memory_plot(data, output_dir):
    time_series = data.get("time_series_data", [])
    times = [tick["relative_time_seconds"] for tick in time_series]
    mem_usage = [tick["failed_run"].get("memory_working_set_gb", 0) for tick in time_series]
    
    limit_gb = data.get("hardware_limits", {}).get("kube_apiserver_memory_limit_gb")

    fig, ax = plt.subplots()
    ax.plot(times, mem_usage, color='purple', linewidth=2, label='Memory Working Set (GB)')
    
    if limit_gb:
        ax.axhline(limit_gb, color='red', linestyle='dashed', linewidth=2, label=f'Limit ({limit_gb}GB)')
        ax.set_ylim(0, limit_gb * 1.1)

    ax.axvline(0, color='black', linestyle=':', label='T=0')
    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('Memory (GB)')
    ax.legend(loc='upper left')
    plt.title('Dimension 4: Memory Exhaustion')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim4_memory.png'))
    plt.close()

def generate_etcd_heatmap(data, output_dir):
    time_series = data.get("time_series_data", [])
    if not time_series:
        return
        
    times = [tick["relative_time_seconds"] for tick in time_series]
    
    # Identify all possible buckets
    buckets = set()
    for tick in time_series:
        buckets.update(tick["failed_run"].get("etcd_fsync_buckets", {}).keys())
    
    # Sort buckets numerically where possible, put '+Inf' last
    def bucket_sort_key(b):
        if b == '+Inf': return float('inf')
        try: return float(b)
        except ValueError: return float('inf')
        
    sorted_buckets = sorted(list(buckets), key=bucket_sort_key)
    
    heatmap_data = np.zeros((len(sorted_buckets), len(times)))
    
    for c_idx, tick in enumerate(time_series):
        b_data = tick["failed_run"].get("etcd_fsync_buckets", {})
        for r_idx, b in enumerate(sorted_buckets):
            heatmap_data[r_idx, c_idx] = b_data.get(b, 0)
            
    df = pd.DataFrame(heatmap_data, index=sorted_buckets, columns=[int(t) for t in times])

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.heatmap(df, cmap="YlGnBu", cbar_kws={'label': 'Fsync Count'}, ax=ax)
    
    # Try to draw the 50ms line if '0.05' exists
    if '0.05' in sorted_buckets:
        idx = sorted_buckets.index('0.05')
        ax.axhline(idx, color='red', linestyle='dashed', linewidth=2, label='50ms Critical Threshold')
        plt.legend()
        
    ax.set_xlabel('Relative Time (seconds)')
    ax.set_ylabel('Disk Save Time (Fsync Bucket)')
    plt.title('Dimension 5: Etcd Disk Health (Heatmap)\n(Are the hard drives too slow?)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'dim5_etcd_heatmap.png'))
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
    generate_etcd_heatmap(data, args.output_dir)
    
    print(f"Visualizations successfully generated in: {args.output_dir}")

if __name__ == "__main__":
    main()