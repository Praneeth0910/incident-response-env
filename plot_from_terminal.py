import re
import matplotlib.pyplot as plt

log_file = "train_log.txt"

losses = []
epochs = []
lrs = []

with open(log_file, "r", encoding="utf-8") as f:
    for line in f:
        if "'loss':" in line:
            try:
                loss = float(re.search(r"'loss': '([0-9.e-]+)'", line).group(1))
                epoch = float(re.search(r"'epoch': '([0-9.e-]+)'", line).group(1))
                lr = float(re.search(r"'learning_rate': '([0-9.e-]+)'", line).group(1))

                losses.append(loss)
                epochs.append(epoch)
                lrs.append(lr)
            except:
                continue

if len(losses) == 0:
    print("❌ No loss data found. Check log format.")
    exit()

# Rolling average
window = 10
rolling = []
for i in range(len(losses)):
    start = max(0, i - window)
    rolling.append(sum(losses[start:i+1]) / (i - start + 1))

# Trend line
import numpy as np
x = np.arange(len(losses))
trend = np.poly1d(np.polyfit(x, losses, 1))(x)

# Plot
plt.figure(figsize=(12, 6))

plt.plot(losses, alpha=0.3, label="Raw loss")
plt.plot(rolling, linewidth=2, label="Smoothed loss")
plt.plot(trend, linestyle="--", label="Trend")

plt.title("SRE Agent Training Curve (Loss)")
plt.xlabel("Steps")
plt.ylabel("Loss")
plt.legend()
plt.grid(True)

# Stats box
plt.text(
    0.02, 0.95,
    f"Steps: {len(losses)}\nFinal Loss: {losses[-1]:.4f}\nBest Loss: {min(losses):.4f}",
    transform=plt.gca().transAxes,
    bbox=dict(facecolor='white', alpha=0.7)
)

plt.tight_layout()
plt.savefig("training_curve.png")
plt.show()