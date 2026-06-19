import matplotlib.pyplot as plt
import numpy as np

# Select 3 most extreme failures and 3 baseline successes
runs = ['2064...', '2066...', '2067...', '2062...', '2057...', '2063...']
durations = [230.7, 204.6, 196.0, 169.4, 171.1, 154.2]
list_requests = [852, 794, 784, 199, 192, 192]

x = np.arange(len(runs))  # the label locations
width = 0.35  # the width of the bars

fig, ax1 = plt.subplots(figsize=(10, 6))

# Highlight background to clearly separate good vs bad
ax1.axvspan(-0.5, 2.5, facecolor='red', alpha=0.1)
ax1.axvspan(2.5, 5.5, facecolor='green', alpha=0.1)

# Annotate zones explicitly at the top
ax1.text(0.25, 1.02, 'FAILED RUNS\n(Death Spiral)', transform=ax1.transAxes, ha='center', va='bottom', fontsize=12, fontweight='bold', color='darkred')
ax1.text(0.75, 1.02, 'SUCCESSFUL RUNS\n(Healthy Baseline)', transform=ax1.transAxes, ha='center', va='bottom', fontsize=12, fontweight='bold', color='darkgreen')

color_dur = 'tab:red'
ax1.set_xlabel('Build ID', fontweight='bold', labelpad=10)
ax1.set_ylabel('Total Test Duration (minutes)', color=color_dur, fontweight='bold')
rects1 = ax1.bar(x - width/2, durations, width, label='Test Duration (min)', color=color_dur, edgecolor='black', alpha=0.8)
ax1.tick_params(axis='y', labelcolor=color_dur)

ax2 = ax1.twinx()  

color_list = 'tab:blue'
ax2.set_ylabel('watch-list LIST Requests', color=color_list, fontweight='bold')
rects2 = ax2.bar(x + width/2, list_requests, width, label='LIST Requests', color=color_list, edgecolor='black', alpha=0.8)
ax2.tick_params(axis='y', labelcolor=color_list)

plt.title('Correlation: Test Duration vs. Pathological LIST Requests', y=1.15, fontweight='bold', fontsize=14)
ax1.set_xticks(x)
ax1.set_xticklabels(runs, fontweight='bold', rotation=45, ha='right')

# Combine legends
lines, labels = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax2.legend(lines + lines2, labels + labels2, loc="upper right")

fig.tight_layout()

plt.savefig('/usr/local/google/home/seans/go/src/github.com/seans3/ci-test-agents/triage-journals/2067291549904932864/visualizations/death_spiral.png', bbox_inches='tight')
