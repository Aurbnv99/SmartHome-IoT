import json
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.gridspec as gridspec
import numpy as np
import os

HISTORY_FILE = "dashboard_data.json"
WINDOW       = 60   # secondi di cronologia da visualizzare

# ── Configurazione Layout ─────────────────────────────────────────────────────
plt.style.use('dark_background')
fig = plt.figure(figsize=(13, 8))
fig.patch.set_facecolor('#0d1117')

# GridSpec per un controllo granulare degli spazi
gs = gridspec.GridSpec(2, 2, figure=fig,
                       height_ratios=[3, 1],
                       hspace=0.35, wspace=0.25)

ax_main = fig.add_subplot(gs[0, :])    # Sopra: Carico Totale vs AI
ax_furn = fig.add_subplot(gs[1, 0])    # Sotto-sinistra: Caldaia/Fornace
ax_appl = fig.add_subplot(gs[1, 1])    # Sotto-destra: Altri elettrodomestici

for ax in [ax_main, ax_furn, ax_appl]:
    ax.set_facecolor('#161b22')
    ax.tick_params(colors='#8b949e')
    ax.xaxis.label.set_color('#8b949e')
    ax.yaxis.label.set_color('#8b949e')
    for spine in ax.spines.values():
        spine.set_color('#30363d')

# Linee dei grafici
line_actual, = ax_main.plot([], [], color='#00ffcc', lw=2, label='Actual Load (kW)')
line_pred,   = ax_main.plot([], [], color='#ff79c6', lw=2, linestyle='--', label='AI Prediction (kW)')
line_furn,   = ax_furn.plot([], [], color='#f4a261', lw=1.8, label='Furnace (kW)')
line_dish,   = ax_appl.plot([], [], color='#4cc9f0', lw=1.5, label='Dishwasher (kW)')
line_mw,     = ax_appl.plot([], [], color='#ffd166', lw=1.5, label='Microwave (kW)')

# Titoli e legende
ax_main.set_title('Live Smart Home Inference: Actual vs AI (1s Resolution)', fontsize=13, fontweight='bold', color='white', pad=15)
ax_main.set_ylabel('Power (kW)', fontsize=11)
ax_main.legend(loc='upper left', facecolor='#21262d', edgecolor='#30363d', labelcolor='white')
ax_main.grid(True, alpha=0.1)

ax_furn.set_title('Furnace Load', fontsize=10, color='#f4a261')
ax_furn.set_ylabel('kW', fontsize=9)
ax_furn.grid(True, alpha=0.1)

ax_appl.set_title('Other Appliances', fontsize=10, color='#4cc9f0')
ax_appl.set_ylabel('kW', fontsize=9)
ax_appl.grid(True, alpha=0.1)

# Box di stato (in alto a destra del grafico principale)
status_text = ax_main.text(0.99, 0.95, '', transform=ax_main.transAxes,
                           color='#ffd166', fontsize=9, va='top', ha='right',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='#21262d', edgecolor='#30363d', alpha=0.9))

# ── Callback di Animazione ────────────────────────────────────────────────────
def animate(_i):
    if not os.path.exists(HISTORY_FILE):
        status_text.set_text("Waiting for data file...")
        return

    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except (json.JSONDecodeError, IOError):
        # Evita crash se il file è momentaneamente vuoto o bloccato
        return

    if not history:
        return

    # Prende gli ultimi WINDOW secondi
    recent = history[-WINDOW:]
    x_data = list(range(len(recent)))

    y_actual = [r.get('house', 0)      for r in recent]
    y_pred   = [r.get('prediction', 0) for r in recent]
    y_furn   = [r.get('furnace', 0)    for r in recent]
    y_dish   = [r.get('dishwasher', 0) for r in recent]
    y_mw     = [r.get('microwave', 0)  for r in recent]

    model_ready = recent[-1].get('model_ready', True)

    # Aggiornamento Main Chart
    line_actual.set_data(x_data, y_actual)
    line_pred.set_data(x_data, y_pred)
    ax_main.set_xlim(0, WINDOW)
    
    all_main_vals = y_actual + y_pred
    if all_main_vals:
        ax_main.set_ylim(max(0, min(all_main_vals) - 0.1), max(all_main_vals) + 0.2)

    # Aggiornamento Furnace
    line_furn.set_data(x_data, y_furn)
    ax_furn.set_xlim(0, WINDOW)
    if y_furn:
        ax_furn.set_ylim(0, max(max(y_furn) + 0.1, 0.5))

    # Aggiornamento Altri Elettrodomestici
    line_dish.set_data(x_data, y_dish)
    line_mw.set_data(x_data, y_mw)
    ax_appl.set_xlim(0, WINDOW)
    combined = y_dish + y_mw
    if combined:
        ax_appl.set_ylim(0, max(max(combined) + 0.05, 0.2))

    # Testo di stato
    ts     = recent[-1].get('timestamp', '--:--:--')
    cur_kw = y_actual[-1] if y_actual else 0.0
    prd_kw = y_pred[-1]   if y_pred   else 0.0
    temp   = recent[-1].get('temp', 0.0)

    if model_ready:
        mae   = float(np.mean(np.abs(np.array(y_actual) - np.array(y_pred))))
        delta = abs(cur_kw - prd_kw)
        status = (f"[{ts}]  Actual: {cur_kw:.3f} kW  |  Pred: {prd_kw:.3f} kW\n"
                  f"Δ: {delta:.3f} kW  |  MAE (rolling): {mae:.3f} kW  |  Temp: {temp:.1f}°C")
        status_text.set_color('#ffd166')
    else:
        status = (f"[{ts}]  Buffering model... ({len(recent)}/{WINDOW}s)\n"
                  f"Actual Load: {cur_kw:.3f} kW")
        status_text.set_color('#ff9900')

    status_text.set_text(status)

# ── Lancio ───────────────────────────────────────────────────────────────────
# Rimuoviamo tight_layout per usare subplots_adjust che non genera warning con GridSpec
fig.suptitle('SMART HOME ENERGY MONITOR - AI PREDICTION', 
             fontsize=16, fontweight='bold', color='white', y=0.96)

plt.subplots_adjust(top=0.88, bottom=0.08, left=0.08, right=0.95, hspace=0.4)

ani = animation.FuncAnimation(fig, animate, interval=1000, cache_frame_data=False)
plt.show()