#!/usr/bin/env python3
"""
fermentation_sim.py
-------------------
Kombucha Fermentation Simulation Model
BSC project – Ruben Schmid

Uses the EXACT same regression model as xsimulation.ch/kombucha/
Based on regression_models.json + predict_time_series.js

The predictTimeSeries function is a direct Python port of the JS:
  coefficients[i] are multiplied by factorValues to get polynomial
  coefficients, then evaluated as a polynomial in t.

Factors order (matches website):
  [tea_g_l, inoculum_pct, sugar_g_l, temp_c, is_green_tea (0|1)]

Variables predicted:
  AAB, Acetic acid, Ethanol, Fructose, Glucose, Sucrose, Yeasts, pH

Usage as module:
    from fermentation_sim import FermentationSim, SimConfig
    sim = FermentationSim(SimConfig(tea_g_l=8, inoculum_pct=10,
                                    sugar_g_l=100, temp_c=25))
    sim.save_csv("simulation_curve.csv")
    result = sim.check_deviation(day=3.0, measured_ph=3.8, measured_temp=24.5)

Standalone:
    python3 fermentation_sim.py --tea 8 --sugar 100 --inoculum 10 --temp 25
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ════════════════════════════════════════════════════════════
#  Regression model data  (from regression_models.json)
# ════════════════════════════════════════════════════════════

REGRESSION_MODELS = {
    "AAB": {
        "coefficients": [
            [0.000914557, 0.0020938132, 0.0000831673, 0.00078099, -0.0026526807],
            [-0.0158732721, -0.0374829412, -0.0014004562, -0.0139751499, 0.0447412656],
            [0.0655361602, 0.1684149179, 0.0068323746, 0.052462907, -0.1306191047],
            [-0.0926880611, 0.0411578701, -0.0176235247, -0.0822028736, 0.6907563872],
        ],
        "intercepts": [-0.0520972078, 0.9003603653, -3.5871667261, 8.2511056014],
    },
    "Acetic acid": {
        "coefficients": [
            [-0.0955353888, 0.0670795616, 0.0122875266, -0.314072159, -6.6216058277],
            [4.1384912694, -2.5959445436, -0.4625394247, 4.2659516978, 159.6595251532],
            [4.2615215414, 36.9569055071, -0.3775680751, 7.6202360629, -482.1927877612],
            [-17.996937694, 40.8018483572, -2.7576849055, -9.9557652094, 123.09281406],
        ],
        "intercepts": [9.2139239975, -81.3207608466, -378.9156229394, 731.9236972167],
    },
    "Ethanol": {
        "coefficients": [
            [-0.000726792, 0.0003383457, 0.0000236396, 0.0000423993, 0.0078866301],
            [0.0087309636, -0.0086863188, -0.0004232297, -0.0014589302, -0.1265709079],
            [-0.0145745818, 0.0333123594, -0.0003968583, 0.0314966905, 0.2781422965],
            [-0.041964643, 0.0656871069, -0.0066857125, -0.0270857419, 0.2827304623],
        ],
        "intercepts": [-0.0059623596, 0.1716736231, -0.6175941978, 1.7824315529],
    },
    "Fructose": {
        "coefficients": [
            [0.0000093427, -0.0009106349, -0.0000478799, 0.0000621107, 0.0053949183],
            [-0.0039632648, 0.0169074379, 0.001221828, -0.0071440456, -0.0794396185],
            [-0.0137714671, -0.0741081296, -0.0032444939, 0.0331212071, 0.6560940921],
            [-0.0180734969, 0.0589413256, -0.0021557604, -0.0151178861, 0.0799148228],
        ],
        "intercepts": [-0.0002901517, 0.1432422051, 0.1475629489, 1.1366059797],
    },
    "Glucose": {
        "coefficients": [
            [0.0010736368, -0.0002104115, 0.0000197347, 0.0009137555, -0.0000766707],
            [-0.0204043085, 0.005196682, 0.0001146307, -0.0216301172, 0.0166450298],
            [0.0395389054, -0.0055119328, 0.0026199992, 0.0860519513, 0.4683353861],
            [-0.0263263081, 0.0309007252, -0.0064671917, -0.0224956546, 0.1946933916],
        ],
        "intercepts": [-0.0535791124, 1.031485488, -3.2897269867, 1.5059237747],
    },
    "Sucrose": {
        "coefficients": [
            [0.0011799628, -0.0004673742, -0.0000625602, -0.0002018789, 0.0011254509],
            [-0.0087103387, 0.0100763494, 0.0005920433, 0.0207451153, -0.0452689444],
            [0.0012781778, -0.0446743546, -0.0019391703, -0.1826116735, -0.6119692537],
            [0.8144686618, -0.2737765874, 0.8734124761, 0.2225724308, -1.8858668275],
        ],
        "intercepts": [0.0496294503, -1.4057368531, 5.3525252271, -8.532365405],
    },
    "Yeasts": {
        "coefficients": [
            [0.0001776287, -0.0001136979, 0.0000094496, 0.0002021042, -0.0012839782],
            [-0.0027792719, 0.0039682846, -0.0001501443, -0.003211714, 0.0173093611],
            [0.0100768579, -0.0392648024, 0.0006282478, 0.0096973402, -0.0641695655],
            [0.0429770291, 0.1280909249, 0.0016083526, 0.0217987903, -0.068382911],
        ],
        "intercepts": [-0.0049911321, 0.0295265893, 0.5095695829, 3.4834785386],
    },
    "pH": {
        "coefficients": [
            [-0.0000817803, -0.0001139006, 0.0000011764, -0.0000915139, 0.0009666847],
            [0.0019478311, -0.0001899, -0.0000099628, 0.0027958234, -0.0171004229],
            [-0.0147216027, 0.0349431275, -0.0002905972, -0.0214892265, 0.0555988541],
            [0.0389089096, -0.2385287769, 0.0054648467, 0.0253306726, -0.201464294],
        ],
        "intercepts": [0.0035783221, -0.0726736351, 0.1674519112, 5.3652541019],
    },
}


# ════════════════════════════════════════════════════════════
#  Core prediction function  (direct port of predict_time_series.js)
# ════════════════════════════════════════════════════════════

def predict_time_series(variable: str, factor_values: list, time_array: list) -> list:
    """
    Port of predictTimeSeries() from predict_time_series.js

    factor_values = [tea_g_l, inoculum_pct, sugar_g_l, temp_c, is_green_tea]
    Returns list of predicted values, one per time point.
    """
    model = REGRESSION_MODELS[variable]
    coeffs_raw  = model["coefficients"]   # shape: [degree+1][n_factors]
    intercepts  = model["intercepts"]     # shape: [degree+1]

    # Each polynomial coefficient = dot(coeffs_raw[i], factor_values) + intercepts[i]
    poly_coeffs = [
        sum(c * f for c, f in zip(coeffs_raw[i], factor_values)) + intercepts[i]
        for i in range(len(intercepts))
    ]

    degree = len(poly_coeffs) - 1   # highest power = degree

    def evaluate(t: float) -> float:
        # poly_coeffs[0]*t^degree + poly_coeffs[1]*t^(degree-1) + ... + poly_coeffs[degree]
        return sum(
            poly_coeffs[i] * (t ** (degree - i))
            for i in range(len(poly_coeffs))
        )

    return [evaluate(t) for t in time_array]


# ════════════════════════════════════════════════════════════
#  Configuration
# ════════════════════════════════════════════════════════════

@dataclass
class SimConfig:
    # Recipe — matches website sliders
    tea_g_l:        float = 8.0     # g/L  (1–10)
    inoculum_pct:   float = 10.0    # %    (1–10)
    sugar_g_l:      float = 100.0   # g/L  (40–100)
    temp_c:         float = 25.0    # °C   (20–30)  target / starting estimate
    is_green_tea:   bool  = False   # False = black tea

    # Temperature mode
    #   "static"  – use temp_c for the entire run (original behaviour)
    #   "dynamic" – feed measured HTU21D readings into the model via
    #               sim.update_temp(); expected values update each cycle
    #               using the time-weighted mean of all readings so far.
    #               temp_c is still used as the target for the temp-deviation
    #               alert and as the fallback before the first reading arrives.
    temp_mode:      str   = "static"   # "static" | "dynamic"

    # Run
    total_days:     float = 10.0
    steps_per_day:  int   = 10      # time resolution (10 → 0.1 d steps)

    # Deviation tolerances
    tol_ph:         float = 0.3
    tol_temp_c:     float = 2.0


# ════════════════════════════════════════════════════════════
#  Result dataclasses
# ════════════════════════════════════════════════════════════

@dataclass
class TimePoint:
    t:           float
    pH:          float
    sucrose:     float   # g/L
    glucose:     float   # g/L
    fructose:    float   # g/L
    ethanol:     float   # g/L
    acetic_acid: float   # mg/L
    yeasts:      float   # log10 KBE/ml
    aab:         float   # log10 KBE/ml


@dataclass
class DeviationVar:
    name:      str
    expected:  float
    measured:  float
    deviation: float
    tolerance: float
    status:    str   # "ok" | "warn" | "alert"


@dataclass
class DeviationResult:
    day:           float
    any_deviation: bool
    variables:     list
    timestamp:     str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


# ════════════════════════════════════════════════════════════
#  Simulation class
# ════════════════════════════════════════════════════════════

class FermentationSim:

    def __init__(self, config: SimConfig):
        self.cfg   = config
        self.curve = self._compute()           # always built with cfg.temp_c
        self._temp_history: list = []          # (day, temp) pairs — dynamic mode

    # ── Public API ───────────────────────────────────────────

    def update_temp(self, day: float, temp: float) -> None:
        """Record a temperature reading for dynamic-mode updates.

        Has no effect in static mode.  Call this every time the HTU21D
        returns a new measurement so the expected-value calculations stay
        in sync with the actual room temperature.
        """
        if self.cfg.temp_mode == "dynamic":
            self._temp_history.append((day, temp))

    def effective_temp(self, up_to_day: float) -> float:
        """Return the temperature the model is currently using.

        Static mode  → always cfg.temp_c.
        Dynamic mode → arithmetic mean of all recorded readings up to
                       up_to_day (equally-spaced 15-min samples make this
                       equivalent to a proper time-weighted integral).
                       Falls back to cfg.temp_c until the first reading
                       arrives.
        """
        if self.cfg.temp_mode != "dynamic":
            return self.cfg.temp_c
        pts = [t for d, t in self._temp_history if d <= up_to_day + 1e-9]
        if not pts:
            return self.cfg.temp_c
        return round(sum(pts) / len(pts), 3)

    def at(self, day: float) -> TimePoint:
        """Return the expected fermentation state at `day`.

        Dynamic mode with at least one temperature reading: evaluates the
        regression model directly at (day, effective_temp) — no curve
        interpolation needed.
        Static mode (or dynamic before first reading): interpolates from
        the pre-computed curve built with cfg.temp_c.
        """
        if self.cfg.temp_mode == "dynamic" and self._temp_history:
            return self._point_at(day, self.effective_temp(day))
        # ── static / fallback ────────────────────────────────
        if day <= 0:
            return self.curve[0]
        if day >= self.cfg.total_days:
            return self.curve[-1]
        for i in range(1, len(self.curve)):
            b = self.curve[i]
            if b.t >= day:
                a    = self.curve[i - 1]
                frac = (day - a.t) / (b.t - a.t)
                return TimePoint(
                    t           = day,
                    pH          = a.pH          + frac * (b.pH          - a.pH),
                    sucrose     = a.sucrose     + frac * (b.sucrose     - a.sucrose),
                    glucose     = a.glucose     + frac * (b.glucose     - a.glucose),
                    fructose    = a.fructose    + frac * (b.fructose    - a.fructose),
                    ethanol     = a.ethanol     + frac * (b.ethanol     - a.ethanol),
                    acetic_acid = a.acetic_acid + frac * (b.acetic_acid - a.acetic_acid),
                    yeasts      = a.yeasts      + frac * (b.yeasts      - a.yeasts),
                    aab         = a.aab         + frac * (b.aab         - a.aab),
                )
        return self.curve[-1]

    def _point_at(self, day: float, temp: float) -> TimePoint:
        """Evaluate the regression model at a single (day, temp) point.

        Runs 8 single-element polynomial evaluations — fast enough to call
        on every sensor cycle without pre-building a full curve.
        """
        factors = [
            self.cfg.tea_g_l,
            self.cfg.inoculum_pct,
            self.cfg.sugar_g_l,
            temp,
            1 if self.cfg.is_green_tea else 0,
        ]
        t = [day]
        return TimePoint(
            t           = day,
            pH          = round(predict_time_series("pH",          factors, t)[0], 5),
            sucrose     = round(predict_time_series("Sucrose",     factors, t)[0], 5),
            glucose     = round(predict_time_series("Glucose",     factors, t)[0], 5),
            fructose    = round(predict_time_series("Fructose",    factors, t)[0], 5),
            ethanol     = round(predict_time_series("Ethanol",     factors, t)[0], 5),
            acetic_acid = round(predict_time_series("Acetic acid", factors, t)[0], 3),
            yeasts      = round(predict_time_series("Yeasts",      factors, t)[0], 5),
            aab         = round(predict_time_series("AAB",         factors, t)[0], 5),
        )

    def check_deviation(
        self,
        day:           float,
        measured_ph:   Optional[float] = None,
        measured_temp: Optional[float] = None,
    ) -> DeviationResult:
        target = self.at(day)
        devs   = []

        if measured_ph is not None:
            d = abs(measured_ph - target.pH)
            devs.append(DeviationVar(
                name      = "pH",
                expected  = round(target.pH, 3),
                measured  = round(measured_ph, 3),
                deviation = round(d, 4),
                tolerance = self.cfg.tol_ph,
                status    = _classify(d, self.cfg.tol_ph),
            ))

        if measured_temp is not None:
            d = abs(measured_temp - self.cfg.temp_c)
            devs.append(DeviationVar(
                name      = "temp_c",
                expected  = self.cfg.temp_c,
                measured  = round(measured_temp, 2),
                deviation = round(d, 3),
                tolerance = self.cfg.tol_temp_c,
                status    = _classify(d, self.cfg.tol_temp_c),
            ))

        return DeviationResult(
            day           = day,
            any_deviation = any(v.status != "ok" for v in devs),
            variables     = devs,
        )

    def save_csv(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        fields = [
            "day", "pH", "sucrose_g_l", "glucose_g_l", "fructose_g_l",
            "ethanol_g_l", "acetic_acid_mg_l", "yeasts_log10_kbe_ml",
            "aab_log10_kbe_ml",
        ]
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for p in self.curve:
                w.writerow({
                    "day":                 round(p.t, 4),
                    "pH":                  round(p.pH, 4),
                    "sucrose_g_l":         round(p.sucrose, 4),
                    "glucose_g_l":         round(p.glucose, 4),
                    "fructose_g_l":        round(p.fructose, 4),
                    "ethanol_g_l":         round(p.ethanol, 4),
                    "acetic_acid_mg_l":    round(p.acetic_acid, 2),
                    "yeasts_log10_kbe_ml": round(p.yeasts, 4),
                    "aab_log10_kbe_ml":    round(p.aab, 4),
                })
        print(f"[sim] Curve saved → {path}  ({len(self.curve)} rows)")

    def print_table(self, every_n_days: float = 1.0) -> None:
        header = (
            f"{'Day':>5}  {'pH':>6}  {'Sucrose':>9}  {'Glucose':>9}  "
            f"{'Fructose':>9}  {'Ethanol':>9}  {'Acetic(mg/L)':>13}  "
            f"{'Yeasts':>8}  {'AAB':>8}"
        )
        cfg = self.cfg
        print(f"\n{'=' * len(header)}")
        print("  Simulated Fermentation Curve  (xsimulation.ch model)")
        print(f"  Tea {cfg.tea_g_l} g/L | Sugar {cfg.sugar_g_l} g/L | "
              f"Inoculum {cfg.inoculum_pct}% | Temp {cfg.temp_c}°C | "
              f"{'Green' if cfg.is_green_tea else 'Black'} tea")
        print(f"{'=' * len(header)}")
        print(header)
        print(f"{'-' * len(header)}")

        day = 0.0
        while day <= self.cfg.total_days + 1e-9:
            p = self.at(day)
            print(
                f"{p.t:>5.1f}  {p.pH:>6.3f}  {p.sucrose:>9.2f}  {p.glucose:>9.2f}  "
                f"{p.fructose:>9.2f}  {p.ethanol:>9.3f}  {p.acetic_acid:>13.1f}  "
                f"{p.yeasts:>8.3f}  {p.aab:>8.3f}"
            )
            day += every_n_days
        print(f"{'=' * len(header)}\n")

    # ── Internal ─────────────────────────────────────────────

    def _compute(self) -> list:
        cfg  = self.cfg
        n    = int(cfg.total_days * cfg.steps_per_day)
        time = [i / cfg.steps_per_day for i in range(n + 1)]

        # Factor vector matches website order exactly
        factors = [
            cfg.tea_g_l,
            cfg.inoculum_pct,
            cfg.sugar_g_l,
            cfg.temp_c,
            1 if cfg.is_green_tea else 0,
        ]

        # Run regression for each variable
        ph_vals      = predict_time_series("pH",          factors, time)
        sucrose_vals  = predict_time_series("Sucrose",     factors, time)
        glucose_vals  = predict_time_series("Glucose",     factors, time)
        fructose_vals = predict_time_series("Fructose",    factors, time)
        ethanol_vals  = predict_time_series("Ethanol",     factors, time)
        acetic_vals   = predict_time_series("Acetic acid", factors, time)
        yeasts_vals   = predict_time_series("Yeasts",      factors, time)
        aab_vals      = predict_time_series("AAB",         factors, time)

        curve = []
        for i, t in enumerate(time):
            curve.append(TimePoint(
                t           = round(t, 6),
                pH          = round(ph_vals[i], 5),
                sucrose     = round(sucrose_vals[i], 5),
                glucose     = round(glucose_vals[i], 5),
                fructose    = round(fructose_vals[i], 5),
                ethanol     = round(ethanol_vals[i], 5),
                acetic_acid = round(acetic_vals[i], 3),
                yeasts      = round(yeasts_vals[i], 5),
                aab         = round(aab_vals[i], 5),
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
    parser.add_argument("--csv",      type=str, default=DEFAULT_CSV)
    parser.add_argument("--no-plot",  action="store_true")
    args = parser.parse_args()

    cfg = SimConfig(
        tea_g_l      = args.tea,
        inoculum_pct = args.inoculum,
        sugar_g_l    = args.sugar,
        temp_c       = args.temp,
        is_green_tea = args.green,
        total_days   = args.days,
    )

    print(f"\n[sim] Recipe: tea={cfg.tea_g_l} g/L  sugar={cfg.sugar_g_l} g/L  "
          f"inoculum={cfg.inoculum_pct}%  temp={cfg.temp_c}°C  "
          f"{'green' if cfg.is_green_tea else 'black'} tea  {cfg.total_days} d")

    sim = FermentationSim(cfg)
    sim.print_table()
    sim.save_csv(args.csv)

    if not args.no_plot:
        try:
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec

            ts = [p.t for p in sim.curve]
            fig = plt.figure(figsize=(14, 10), facecolor="#0d1117")
            fig.suptitle(
                f"Kombucha Simulation — Tea {cfg.tea_g_l}g/L  Sugar {cfg.sugar_g_l}g/L  "
                f"Inoculum {cfg.inoculum_pct}%  Temp {cfg.temp_c}°C",
                color="#e6edf3", fontsize=12, y=0.98
            )
            gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

            axes_cfg = [
                (gs[0, 0], "pH",          [("pH",         "#e86bdf")]),
                (gs[0, 1], "Sugars [g/L]",[("sucrose",    "#d4a843"),
                                           ("glucose",    "#5e9f6e"),
                                           ("fructose",   "#4fc3f7")]),
                (gs[1, 0], "Acids / EtOH",[("ethanol",    "#ff8a65"),
                                           ("acetic_acid","#ef5350")]),
                (gs[1, 1], "Biomass [log₁₀]", [("yeasts", "#ab47bc"),
                                               ("aab",    "#26c6da")]),
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
                ax.legend(fontsize=7, facecolor="#161b22",
                          labelcolor="#e6edf3", edgecolor="#21262d")

            out_png = args.csv.replace(".csv", ".png")
            plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor="#0d1117")
            print(f"[sim] Plot saved  → {out_png}")
            plt.show()

        except ImportError:
            print("[sim] matplotlib not installed — skipping plot.")

    # Quick deviation demo
    print("\n[sim] Deviation check demo (day=3.0, pH=3.8, temp=24.5):")
    result = sim.check_deviation(day=3.0, measured_ph=3.8, measured_temp=24.5)
    for v in result.variables:
        flag = {"ok": "✅", "warn": "⚠️ ", "alert": "❌"}[v.status]
        print(f"  {flag}  {v.name:<12} expected={v.expected}  "
              f"measured={v.measured}  dev={v.deviation}  tol=±{v.tolerance}")


if __name__ == "__main__":
    main()
