#!/usr/bin/env python3
"""
fermentation_sim.py
-------------------
Kombucha Fermentation Simulation Model
BSC project – Ruben Schmid

PURPOSE
-------
Pre-computes a full fermentation recipe curve at startup and writes it to a
CSV file.  During the run the main data-collection loop calls
`check_deviation()` with each live sensor reading; the function returns a
structured result dict that can be used to trigger alerts, write logs, etc.

The model is a mechanistic approximation based on:
  Jayabalan et al. (2014)  – Kombucha biochemistry review
  Laureys & De Vuyst (2014) – microbial dynamics

USAGE
-----
As a module (recommended):

    from fermentation_sim import FermentationSim, SimConfig

    cfg = SimConfig(
        tea_g_l        = 8,
        inoculum_pct   = 10,
        sugar_g_l      = 100,
        temp_c         = 25,
        is_green_tea   = False,
        total_days     = 10,
        tol_ph         = 0.3,
        tol_temp_c     = 2.0,
    )
    sim = FermentationSim(cfg)
    sim.save_csv("/home/schmiru/Kombucha_Fermentation/simulation_curve.csv")

    # later, inside the sensor loop:
    result = sim.check_deviation(day=2.5, measured_ph=3.9, measured_temp=24.1)
    if result["any_deviation"]:
        for v in result["variables"]:
            if v["status"] != "ok":
                print(v)   # hand off to alert pipeline

Standalone (for inspection / plotting):

    python3 fermentation_sim.py

Install once:
    pip3 install matplotlib   # only needed for standalone plot
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ════════════════════════════════════════════════════════════
#  Configuration dataclass  –  fill in your recipe here
# ════════════════════════════════════════════════════════════

@dataclass
class SimConfig:
    # ── Recipe parameters ───────────────────────────────────
    tea_g_l:        float = 8.0    # tea concentration  [g/L]
    inoculum_pct:   float = 10.0   # starter volume     [%]
    sugar_g_l:      float = 100.0  # initial sucrose    [g/L]
    temp_c:         float = 25.0   # fermentation temp  [°C]
    is_green_tea:   bool  = False   # False = black tea

    # ── Run parameters ──────────────────────────────────────
    total_days:     float = 10.0   # total fermentation duration
    steps_per_day:  int   = 48     # time resolution (48 → 30-min steps)

    # ── Deviation tolerances ─────────────────────────────────
    tol_ph:         float = 0.3    # pH units
    tol_temp_c:     float = 2.0    # °C


# ════════════════════════════════════════════════════════════
#  Simulation result dataclasses
# ════════════════════════════════════════════════════════════

@dataclass
class TimePoint:
    """One row of the simulated curve."""
    t:          float   # day
    pH:         float
    sucrose:    float   # g/L
    glucose:    float   # g/L
    fructose:   float   # g/L
    ethanol:    float   # g/L
    acetic_acid: float  # mg/L
    yeasts:     float   # log10 KBE/ml
    aab:        float   # log10 KBE/ml


@dataclass
class DeviationVar:
    name:       str
    expected:   float
    measured:   float
    deviation:  float
    tolerance:  float
    status:     str    # "ok" | "warn" | "alert"


@dataclass
class DeviationResult:
    day:          float
    any_deviation: bool
    variables:    list[DeviationVar]
    timestamp:    str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ════════════════════════════════════════════════════════════
#  Core model
# ════════════════════════════════════════════════════════════

class FermentationSim:
    """
    Compute and store the full fermentation curve for a given recipe.
    Thread-safe for reading after construction.
    """

    def __init__(self, config: SimConfig):
        self.cfg   = config
        self.curve: list[TimePoint] = self._compute()

    # ── Public API ───────────────────────────────────────────

    def at(self, day: float) -> TimePoint:
        """Interpolate the simulated curve at any day (float)."""
        if day <= 0:
            return self.curve[0]
        if day >= self.cfg.total_days:
            return self.curve[-1]
        for i in range(1, len(self.curve)):
            b = self.curve[i]
            if b.t >= day:
                a   = self.curve[i - 1]
                f   = (day - a.t) / (b.t - a.t)
                return TimePoint(
                    t           = day,
                    pH          = a.pH          + f * (b.pH          - a.pH),
                    sucrose     = a.sucrose     + f * (b.sucrose     - a.sucrose),
                    glucose     = a.glucose     + f * (b.glucose     - a.glucose),
                    fructose    = a.fructose    + f * (b.fructose    - a.fructose),
                    ethanol     = a.ethanol     + f * (b.ethanol     - a.ethanol),
                    acetic_acid = a.acetic_acid + f * (b.acetic_acid - a.acetic_acid),
                    yeasts      = a.yeasts      + f * (b.yeasts      - a.yeasts),
                    aab         = a.aab         + f * (b.aab         - a.aab),
                )
        return self.curve[-1]

    def check_deviation(
        self,
        day:           float,
        measured_ph:   Optional[float] = None,
        measured_temp: Optional[float] = None,
    ) -> DeviationResult:
        """
        Compare live sensor readings against the recipe target at `day`.

        Parameters
        ----------
        day           : current fermentation day (float, e.g. 2.5)
        measured_ph   : pH reading from the Pico/pH probe (or None to skip)
        measured_temp : temperature from HTU21D (or None to skip)

        Returns
        -------
        DeviationResult with per-variable status and an `any_deviation` flag.
        """
        target  = self.at(day)
        cfg     = self.cfg
        devs: list[DeviationVar] = []

        if measured_ph is not None:
            d = abs(measured_ph - target.pH)
            devs.append(DeviationVar(
                name      = "pH",
                expected  = round(target.pH, 3),
                measured  = round(measured_ph, 3),
                deviation = round(d, 4),
                tolerance = cfg.tol_ph,
                status    = _classify(d, cfg.tol_ph),
            ))

        if measured_temp is not None:
            d = abs(measured_temp - cfg.temp_c)
            devs.append(DeviationVar(
                name      = "temp_c",
                expected  = cfg.temp_c,
                measured  = round(measured_temp, 2),
                deviation = round(d, 3),
                tolerance = cfg.tol_temp_c,
                status    = _classify(d, cfg.tol_temp_c),
            ))

        any_dev = any(v.status != "ok" for v in devs)
        return DeviationResult(day=day, any_deviation=any_dev, variables=devs)

    def save_csv(self, path: str) -> None:
        """
        Write the full simulated curve to a CSV file.
        Creates parent directories if needed.
        The file is overwritten each run (the curve is deterministic).
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fieldnames = [
            "day", "pH", "sucrose_g_l", "glucose_g_l", "fructose_g_l",
            "ethanol_g_l", "acetic_acid_mg_l", "yeasts_log10_kbe_ml", "aab_log10_kbe_ml",
        ]
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for p in self.curve:
                writer.writerow({
                    "day":                   round(p.t, 4),
                    "pH":                    round(p.pH, 4),
                    "sucrose_g_l":           round(p.sucrose, 4),
                    "glucose_g_l":           round(p.glucose, 4),
                    "fructose_g_l":          round(p.fructose, 4),
                    "ethanol_g_l":           round(p.ethanol, 4),
                    "acetic_acid_mg_l":      round(p.acetic_acid, 2),
                    "yeasts_log10_kbe_ml":   round(p.yeasts, 4),
                    "aab_log10_kbe_ml":      round(p.aab, 4),
                })
        print(f"[sim] Curve saved → {path}  ({len(self.curve)} rows)")

    def print_table(self, every_n_days: float = 1.0) -> None:
        """Print a human-readable summary table at integer day intervals."""
        cols = ["day", "pH", "sucrose", "glucose", "fructose",
                "ethanol", "acetic_acid", "yeasts", "aab"]
        header = (
            f"{'Day':>5}  {'pH':>6}  {'Sucrose':>9}  {'Glucose':>9}  "
            f"{'Fructose':>9}  {'Ethanol':>9}  {'Acetic(mg/L)':>13}  "
            f"{'Yeasts':>8}  {'AAB':>8}"
        )
        print("\n" + "=" * len(header))
        print("  Simulated Fermentation Curve")
        cfg = self.cfg
        print(f"  Tea {cfg.tea_g_l} g/L  |  Sugar {cfg.sugar_g_l} g/L  |  "
              f"Inoculum {cfg.inoculum_pct}%  |  Temp {cfg.temp_c}°C  |  "
              f"{'Green' if cfg.is_green_tea else 'Black'} tea")
        print("=" * len(header))
        print(header)
        print("-" * len(header))

        day = 0.0
        while day <= self.cfg.total_days + 1e-9:
            p = self.at(day)
            print(
                f"{p.t:>5.1f}  {p.pH:>6.3f}  {p.sucrose:>9.2f}  {p.glucose:>9.2f}  "
                f"{p.fructose:>9.2f}  {p.ethanol:>9.3f}  {p.acetic_acid:>13.1f}  "
                f"{p.yeasts:>8.3f}  {p.aab:>8.3f}"
            )
            day += every_n_days
        print("=" * len(header) + "\n")

    # ── Internal model ───────────────────────────────────────

    def _compute(self) -> list[TimePoint]:
        cfg  = self.cfg
        dt   = 1.0 / cfg.steps_per_day
        n    = int(round(cfg.total_days * cfg.steps_per_day))

        # Temperature correction (Q10 ≈ 2, reference 25 °C)
        kT = math.pow(2.0, (cfg.temp_c - 25.0) / 10.0)

        # Tea & inoculum factors
        tea_f  = (1.0 + 0.04 * cfg.tea_g_l) * (1.08 if cfg.is_green_tea else 1.0)
        ino_f  = cfg.inoculum_pct / 100.0
        start_pH = 7.0 - 1.2 * ino_f * tea_f

        # Rate constants (per day at 25 °C)
        k_suc   = 0.18 * kT   # sucrose → glucose + fructose
        k_glu   = 0.12 * kT   # yeast consumes glucose
        k_fru   = 0.15 * kT   # yeast consumes fructose
        k_acet  = 0.22 * kT   # AAB: ethanol → acetic acid
        mu_y    = 0.55 * kT   # yeast max growth rate
        mu_a    = 0.40 * kT   # AAB max growth rate
        k_pH    = 0.30 * kT * tea_f  # net acidification rate

        # Initial state
        sucrose  = cfg.sugar_g_l
        glucose  = 0.0
        fructose = 0.0
        ethanol  = 0.0
        acetic   = 0.0          # mg/L
        yeast    = 3.5 + math.log10(cfg.inoculum_pct + 1)
        aab      = 3.2 + math.log10(cfg.inoculum_pct + 1)
        ph       = start_pH

        curve = [TimePoint(0.0, round(ph, 4), sucrose, glucose, fructose,
                           ethanol, acetic, round(yeast, 4), round(aab, 4))]

        for i in range(1, n + 1):
            t = i * dt

            # pH-based inhibition: fermentation stops below ~pH 2.2
            inh = max(0.0, (ph - 2.2) / (4.5 - 2.2))

            # Sucrose hydrolysis
            d_suc  = -k_suc * sucrose * inh * dt
            glucose  += -d_suc * 0.53
            fructose += -d_suc * 0.47
            sucrose  = max(0.0, sucrose + d_suc)

            # Yeast: consume mono-sugars → ethanol
            d_glu = -k_glu * glucose  * inh * dt
            d_fru = -k_fru * fructose * inh * dt
            glucose  = max(0.0, glucose  + d_glu)
            fructose = max(0.0, fructose + d_fru)
            ethanol  = max(0.0, ethanol + (-(d_glu + d_fru)) * 0.46)

            # AAB: ethanol → acetic acid
            d_ac   = k_acet * ethanol * inh * dt
            acetic  += d_ac * 1000.0    # g/L → mg/L
            ethanol  = max(0.0, ethanol - d_ac)

            # Microbial growth (logistic, log10-space)
            y_max, a_max = 7.5, 7.2
            yeast = min(y_max, yeast + mu_y * yeast * (1 - yeast / y_max) * inh * dt)
            aab   = min(a_max, aab   + mu_a * aab   * (1 - aab   / a_max) * inh * dt)

            # pH drop (driven by acetic acid production)
            ph = max(2.2, ph - k_pH * (acetic / 10000.0) * inh * dt)

            curve.append(TimePoint(
                t           = round(t, 6),
                pH          = round(ph, 5),
                sucrose     = round(max(0.0, sucrose), 5),
                glucose     = round(max(0.0, glucose), 5),
                fructose    = round(max(0.0, fructose), 5),
                ethanol     = round(max(0.0, ethanol), 5),
                acetic_acid = round(acetic, 3),
                yeasts      = round(yeast, 5),
                aab         = round(aab, 5),
            ))

        return curve


# ════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════

def _classify(deviation: float, tolerance: float) -> str:
    if deviation <= tolerance:
        return "ok"
    if deviation <= tolerance * 2.0:
        return "warn"
    return "alert"


# ════════════════════════════════════════════════════════════
#  Standalone entry point
# ════════════════════════════════════════════════════════════

DEFAULT_CSV = "/home/schmiru/Kombucha_Fermentation/simulation_curve.csv"

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kombucha fermentation simulator")
    parser.add_argument("--tea",      type=float, default=8.0,   help="Tea [g/L]")
    parser.add_argument("--sugar",    type=float, default=100.0, help="Sucrose [g/L]")
    parser.add_argument("--inoculum", type=float, default=10.0,  help="Starter [%%]")
    parser.add_argument("--temp",     type=float, default=25.0,  help="Temp [°C]")
    parser.add_argument("--days",     type=float, default=10.0,  help="Duration [d]")
    parser.add_argument("--green",    action="store_true",        help="Use green tea")
    parser.add_argument("--csv",      type=str,   default=DEFAULT_CSV, help="CSV output path")
    parser.add_argument("--no-plot",  action="store_true",        help="Skip matplotlib plot")
    args = parser.parse_args()

    cfg = SimConfig(
        tea_g_l      = args.tea,
        inoculum_pct = args.inoculum,
        sugar_g_l    = args.sugar,
        temp_c       = args.temp,
        is_green_tea = args.green,
        total_days   = args.days,
    )

    print(f"\n[sim] Running model …  tea={cfg.tea_g_l} g/L  sugar={cfg.sugar_g_l} g/L  "
          f"inoculum={cfg.inoculum_pct}%  temp={cfg.temp_c}°C  "
          f"{'green' if cfg.is_green_tea else 'black'} tea  {cfg.total_days} d")

    sim = FermentationSim(cfg)
    sim.print_table()
    sim.save_csv(args.csv)

    # ── Optional plot ────────────────────────────────────────
    if not args.no_plot:
        try:
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec

            ts = [p.t for p in sim.curve]

            fig = plt.figure(figsize=(14, 10), facecolor="#0d1117")
            fig.suptitle("Kombucha Fermentation Simulation", color="#e6edf3",
                         fontsize=14, y=0.98)
            gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

            axes_cfg = [
                (gs[0, 0], "pH",         [("pH",        "#e86bdf")]),
                (gs[0, 1], "Sugars [g/L]",[("sucrose",   "#d4a843"),
                                           ("glucose",   "#5e9f6e"),
                                           ("fructose",  "#4fc3f7")]),
                (gs[1, 0], "Acids / EtOH",[("ethanol",   "#ff8a65"),
                                           ("acetic_acid","#ef5350")]),
                (gs[1, 1], "Biomass [log₁₀]",[("yeasts", "#ab47bc"),
                                              ("aab",     "#26c6da")]),
            ]

            for spec, ylabel, series in axes_cfg:
                ax = fig.add_subplot(spec)
                ax.set_facecolor("#161b22")
                ax.tick_params(colors="#8b949e", labelsize=8)
                for spine in ax.spines.values():
                    spine.set_edgecolor("#21262d")
                ax.set_xlabel("Day", color="#8b949e", fontsize=8)
                ax.set_ylabel(ylabel, color="#8b949e", fontsize=8)
                ax.grid(color="#21262d", linewidth=0.5)

                for attr, color in series:
                    vals = [getattr(p, attr) for p in sim.curve]
                    ax.plot(ts, vals, color=color, linewidth=1.5, label=attr)
                ax.legend(fontsize=7, facecolor="#161b22", labelcolor="#e6edf3",
                          edgecolor="#21262d")

            out_png = args.csv.replace(".csv", ".png")
            plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor="#0d1117")
            print(f"[sim] Plot saved  → {out_png}")
            plt.show()

        except ImportError:
            print("[sim] matplotlib not installed — skipping plot.")
            print("      Install with: pip3 install matplotlib")

    # ── Quick deviation demo ─────────────────────────────────
    print("\n[sim] Deviation check demo (day=3.0, pH=4.2, temp=24.0):")
    result = sim.check_deviation(day=3.0, measured_ph=4.2, measured_temp=24.0)
    for v in result.variables:
        flag = {"ok": "✅", "warn": "⚠️ ", "alert": "❌"}[v.status]
        print(f"  {flag}  {v.name:<12} expected={v.expected}  "
              f"measured={v.measured}  dev={v.deviation}  tol=±{v.tolerance}")


if __name__ == "__main__":
    main()
