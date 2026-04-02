"""
stat_test_and_plot.py
──────────────────────
Offline statistical analysis of the gateway's CSV log.

Changes:
  • Removed JSON dependency completely.
  • The script now relies EXCLUSIVELY on real_vs_ai_log.csv to analyze and 
    plot the entire simulation history (hours/days) instead of just the last 5 minutes.
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import stats


# ── helpers ───────────────────────────────────────────────────────────────────

def load_csv(path="real_vs_ai_log.csv"):
    """Load the 60-second-interval CSV written by the gateway."""
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        print(f"[WARN] {path} not found – skipping CSV analysis.")
        return None

    if len(df) < 2:
        print(f"[WARN] {path} has fewer than 2 rows – need more data.")
        return None

    # Robust timestamp parsing: accept both '2024-01-01 11:23:45' and '11:23:45'
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp'])
    return df


def compute_metrics(actual, predicted):
    """Return a dict of error metrics."""
    diff   = actual - predicted
    mae    = np.mean(np.abs(diff))
    rmse   = np.sqrt(np.mean(diff ** 2))
    ss_res = np.sum(diff ** 2)
    ss_tot = np.sum((actual - np.mean(actual)) ** 2)
    r2     = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    t_stat, p_value = stats.ttest_rel(actual, predicted)
    return dict(mae=mae, rmse=rmse, r2=r2, t_stat=t_stat, p_value=p_value)


def print_report(label, df, metrics):
    print(f"\n{'─'*55}")
    print(f"  STATISTICAL ANALYSIS  [{label}]")
    print(f"{'─'*55}")
    print(f"  Data points  : {len(df)}")
    print(f"  Time range   : {df['timestamp'].iloc[0].strftime('%H:%M:%S')}"
          f" → {df['timestamp'].iloc[-1].strftime('%H:%M:%S')}")
    print(f"  MAE          : {metrics['mae']:.4f} kW")
    print(f"  RMSE         : {metrics['rmse']:.4f} kW")
    print(f"  R²           : {metrics['r2']:.4f}")
    print(f"  T-statistic  : {metrics['t_stat']:.4f}")
    print(f"  P-value      : {metrics['p_value']:.4f}")
    if metrics['p_value'] > 0.05:
        print("  Conclusion   : ✓ No significant difference – model is accurate.")
    else:
        print("  Conclusion   : ✗ Significant difference detected – model may be drifting.")
    print(f"{'─'*55}\n")


# ── main ──────────────────────────────────────────────────────────────────────

def run_analysis():
    # Load data exclusively from the CSV historical log
    df_main = load_csv("real_vs_ai_log.csv")
    src_main = "CSV (Full History)"

    if df_main is None:
        print("ERROR: No usable data found in CSV. Run the gateway first to generate logs.")
        sys.exit(1)

    actual    = df_main['actual_load_kw'].values
    predicted = df_main['predicted_load_kw'].values
    metrics   = compute_metrics(actual, predicted)

    print_report(src_main, df_main, metrics)

    # ── Plot ─────────────────────────────────────────────────────────────────
    plt.style.use('seaborn-v0_8-whitegrid')
    fig = plt.figure(figsize=(14, 8))
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.40, wspace=0.30)

    ax_ts  = fig.add_subplot(gs[0, :])   # time-series comparison
    ax_sct = fig.add_subplot(gs[1, 0])   # scatter: actual vs predicted
    ax_err = fig.add_subplot(gs[1, 1])   # error distribution histogram

    # Time-series
    ax_ts.plot(df_main['timestamp'], actual,    color='steelblue',  lw=2,
               label='Actual Load (kW)')
    ax_ts.plot(df_main['timestamp'], predicted, color='tomato',     lw=2,
               linestyle='--', label='AI Prediction (kW)')
    ax_ts.set_title('Real-Time Energy Usage: Actual vs AI Prediction', fontsize=13)
    ax_ts.set_xlabel('Time')
    ax_ts.set_ylabel('Power (kW)')
    ax_ts.legend()
    ax_ts.tick_params(axis='x', rotation=30)

    # Annotation box
    ann = (f"MAE={metrics['mae']:.4f} kW   RMSE={metrics['rmse']:.4f} kW\n"
           f"R²={metrics['r2']:.4f}   p={metrics['p_value']:.4f}")
    ax_ts.text(0.01, 0.97, ann, transform=ax_ts.transAxes,
               fontsize=9, va='top', ha='left',
               bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    # Scatter: actual vs predicted (perfect model → diagonal line)
    lo = min(actual.min(), predicted.min()) - 0.05
    hi = max(actual.max(), predicted.max()) + 0.05
    ax_sct.scatter(actual, predicted, alpha=0.4, s=15, color='steelblue')
    ax_sct.plot([lo, hi], [lo, hi], 'r--', lw=1.5, label='Perfect fit')
    ax_sct.set_xlim(lo, hi)
    ax_sct.set_ylim(lo, hi)
    ax_sct.set_xlabel('Actual (kW)')
    ax_sct.set_ylabel('Predicted (kW)')
    ax_sct.set_title(f'Actual vs Predicted  (R²={metrics["r2"]:.3f})', fontsize=11)
    ax_sct.legend(fontsize=9)

    # Error histogram
    errors = actual - predicted
    ax_err.hist(errors, bins=30, color='steelblue', edgecolor='white', alpha=0.8)
    ax_err.axvline(0, color='red',    lw=1.5, linestyle='--', label='Zero error')
    ax_err.axvline(errors.mean(), color='orange', lw=1.5, linestyle='-.',
                   label=f'Mean={errors.mean():.4f}')
    ax_err.set_xlabel('Prediction Error (kW)')
    ax_err.set_ylabel('Count')
    ax_err.set_title('Error Distribution', fontsize=11)
    ax_err.legend(fontsize=9)

    fig.suptitle('Smart Home AI – Statistical Validation Report',
                 fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()

    out = 'actual_vs_predicted_plot.png'
    plt.savefig(out, dpi=300, bbox_inches='tight')
    print(f"Saved plot → '{out}'")
    plt.show()


if __name__ == "__main__":
    run_analysis()