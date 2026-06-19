import matplotlib.pyplot as plt
import numpy as np

# Data
runs = ['2067... (Fail)', '2066... (Fail)', '2058... (Fail)', '2063... (Success)', '2062... (Success)', '2057... (Success)']
durations = [196, 204, 206, 154, 169, 171]
list_requests = [784, 794, 514, 192, 199, 192]

x = np.arange(len(runs))  # the label locations
width = 0.35  # the width of the bars

fig, ax1 = plt.subplots(figsize=(10, 6))

color = 'tab:red'
ax1.set_xlabel('Build ID')
ax1.set_ylabel('Total Test Duration (minutes)', color=color)
rects1 = ax1.bar(x - width/2, durations, width, label='Duration', color=color, alpha=0.7)
ax1.tick_params(axis='y', labelcolor=color)

ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis

color = 'tab:blue'
ax2.set_ylabel('watch-list LIST Requests', color=color)  # we already handled the x-label with ax1
rects2 = ax2.bar(x + width/2, list_requests, width, label='LIST Requests', color=color, alpha=0.7)
ax2.tick_params(axis='y', labelcolor=color)

# Add some text for labels, title and custom x-axis tick labels, etc.
plt.title('The Death Spiral: Test Duration vs. Pathological LIST Requests')
ax1.set_xticks(x)
ax1.set_xticklabels(runs, rotation=45, ha='right')

# Add legend
fig.tight_layout()  # otherwise the right y-label is slightly clipped
fig.legend(loc="upper left", bbox_to_anchor=(0,1), bbox_transform=ax1.transAxes)

plt.savefig('/usr/local/google/home/seans/go/src/github.com/seans3/ci-test-agents/triage-journals/2067291549904932864/visualizations/death_spiral.png', bbox_inches='tight')
