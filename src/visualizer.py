"""
Fleet Downtime Minimizer - Visualization
MPP30 Manutenção - ITA 2026

Gera todos os gráficos do relatório:
  - Gantt chart da frota (SBs, inspeções, empacotamentos)
  - Perfis de FH acumuladas por aeronave
  - Ocupação do hangar ao longo do tempo
  - Alocação semanal de FH (stacked area)
  - Histograma do downtime do Monte Carlo
"""

import os
from typing import List, Optional
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import MaxNLocator

from src.config import (
    HORIZON_WEEKS, WEEKS_2026,
    SB_DURATION_CEIL,
    HANGAR_CAPACITY, FH_TARGET_2026, FH_TARGET_2027,
)
from src.models import Aircraft, ScheduleResult
from src.simulator import MonteCarloResults


COLORS = {
    "SB": "#E74C3C",          # Vermelho
    "INSP100": "#3498DB",     # Azul
    "INSP200": "#2ECC71",     # Verde
    "INSP400": "#9B59B6",     # Roxo
    "PKG": "#F39C12",         # Laranja (empacotado)
    "AVAILABLE": "#ECF0F1",   # Cinza claro
    "UNAVAILABLE": "#BDC3C7", # Cinza
}


def plot_gantt(
    fleet: List[Aircraft],
    result: ScheduleResult,
    save_path: str = "results/gantt_chart.png",
    title: str = "Schedule de Manutenção da Frota",
):
    """Gera Gantt chart mostrando períodos de SB, inspeções e operação."""
    D = SB_DURATION_CEIL
    n = len(fleet)

    fig, ax = plt.subplots(figsize=(18, 8))

    y_labels = []
    for i, ac in enumerate(fleet):
        y = n - 1 - i  # Inverter para ANV-01 ficar no topo
        y_labels.append(ac.id)

        # Barra base (operacional)
        ax.barh(y, HORIZON_WEEKS, left=1, height=0.6,
                color=COLORS["AVAILABLE"], edgecolor="none", alpha=0.3)

        # Período antes da disponibilidade
        if ac.available_week > 1:
            ax.barh(y, ac.available_week - 1, left=1, height=0.6,
                    color=COLORS["UNAVAILABLE"], edgecolor="none", alpha=0.5)

        # SB
        if ac.index in result.sb_schedule:
            sb_start = result.sb_schedule[ac.index]
            sb_dur = D
            ax.barh(y, sb_dur, left=sb_start, height=0.6,
                    color=COLORS["SB"], edgecolor="black", linewidth=0.5)

            # Inspeções empacotadas dentro do SB
            pkg_milestones = [m for (idx, m) in result.packaged_inspections if idx == ac.index]
            if pkg_milestones:
                # Marcar com padrão sobre a barra de SB
                ax.barh(y, sb_dur, left=sb_start, height=0.6,
                        color="none", edgecolor=COLORS["PKG"],
                        linewidth=2, linestyle="--")

        # Inspeções standalone
        for (ac_idx, milestone, week, dur) in result.standalone_inspections:
            if ac_idx != ac.index:
                continue
            from src.models import get_inspection_level
            level = get_inspection_level(milestone)
            color = COLORS.get(f"INSP{level}", COLORS["INSP100"])
            ax.barh(y, max(dur, 0.5), left=week, height=0.6,
                    color=color, edgecolor="black", linewidth=0.5)

    # Linha vertical separando 2026/2027
    ax.axvline(x=WEEKS_2026 + 0.5, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax.text(WEEKS_2026 / 2, n + 0.3, "2026", ha="center", fontsize=11, fontweight="bold")
    ax.text(WEEKS_2026 + HORIZON_WEEKS / 2 - WEEKS_2026 / 2 + 0.5, n + 0.3,
            "2027", ha="center", fontsize=11, fontweight="bold")

    # Legenda
    legend_patches = [
        mpatches.Patch(color=COLORS["SB"], label="Service Bulletin"),
        mpatches.Patch(color=COLORS["INSP100"], label="Insp 100FH"),
        mpatches.Patch(color=COLORS["INSP200"], label="Insp 200FH"),
        mpatches.Patch(color=COLORS["INSP400"], label="Insp 400FH"),
        mpatches.Patch(facecolor="none", edgecolor=COLORS["PKG"],
                       linestyle="--", linewidth=2, label="Empacotado c/ SB"),
        mpatches.Patch(color=COLORS["UNAVAILABLE"], alpha=0.5, label="Não entregue"),
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=9)

    ax.set_yticks(range(n))
    ax.set_yticklabels(reversed(y_labels), fontsize=10)
    ax.set_xlabel("Semana do planejamento", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlim(0.5, HORIZON_WEEKS + 0.5)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=20))
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Gantt chart salvo em: {save_path}")


def plot_fh_profiles(
    fleet: List[Aircraft],
    result: ScheduleResult,
    save_path: str = "results/fh_profiles.png",
):
    """Gera gráfico dos perfis de FH acumuladas por aeronave ao longo do tempo."""
    D = SB_DURATION_CEIL

    fig, ax = plt.subplots(figsize=(16, 9))
    colors_list = plt.cm.tab10(np.linspace(0, 1, len(fleet)))

    for ac in fleet:
        weeks = []
        fh_cum = []
        fh = ac.fh0

        # Semanas em SB
        sb_start = result.sb_schedule.get(ac.index, None)
        sb_weeks = set()
        if sb_start:
            sb_weeks = set(range(sb_start, sb_start + D))

        for t in range(1, HORIZON_WEEKS + 1):
            if t < ac.available_week:
                continue
            if t not in sb_weeks:
                fh += result.fh_allocation.get((ac.index, t), 0.0)
            weeks.append(t)
            fh_cum.append(fh)

        ax.plot(weeks, fh_cum, label=ac.id, color=colors_list[ac.index],
                linewidth=1.5, alpha=0.8)

        # Marcar período de SB
        if sb_start:
            sb_fh = result.fh_at_sb_entry.get(ac.index, fh)
            ax.plot([sb_start, sb_start + D], [sb_fh, sb_fh],
                    color=colors_list[ac.index], linewidth=3, alpha=0.4)
            ax.scatter([sb_start], [sb_fh], color=colors_list[ac.index],
                       s=30, zorder=5)

    # Linhas horizontais para milestones de inspeção
    for milestone in [100, 200, 300, 400, 500, 600, 700, 800]:
        ax.axhline(y=milestone, color="gray", linestyle=":", linewidth=0.5, alpha=0.5)
        ax.text(HORIZON_WEEKS + 1, milestone, f"{milestone}", fontsize=7,
                va="center", color="gray")

    # Linha vertical 2026/2027
    ax.axvline(x=WEEKS_2026 + 0.5, color="black", linestyle="--",
               linewidth=1, alpha=0.5)

    ax.set_xlabel("Semana do planejamento", fontsize=11)
    ax.set_ylabel("Flight Hours (FH) acumuladas", fontsize=11)
    ax.set_title("Perfis de FH por Aeronave", fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.set_xlim(0, HORIZON_WEEKS + 3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  FH profiles salvo em: {save_path}")


def plot_monte_carlo_histogram(
    mc_results: MonteCarloResults,
    deterministic_downtime: float,
    save_path: str = "results/monte_carlo_histogram.png",
):
    """Gera histograma da distribuição de downtime do Monte Carlo."""
    downtimes = [m.total_downtime for m in mc_results.metrics]

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.hist(downtimes, bins=50, color="#3498DB", edgecolor="white",
            alpha=0.7, density=True, label="Distribuição MC")

    # Linhas verticais para estatísticas
    ax.axvline(mc_results.mean_downtime, color="red", linestyle="-",
               linewidth=2, label=f"Média: {mc_results.mean_downtime:.1f}")
    ax.axvline(mc_results.p5_downtime, color="orange", linestyle="--",
               linewidth=1.5, label=f"P5: {mc_results.p5_downtime:.1f}")
    ax.axvline(mc_results.p95_downtime, color="orange", linestyle="--",
               linewidth=1.5, label=f"P95: {mc_results.p95_downtime:.1f}")
    ax.axvline(deterministic_downtime, color="green", linestyle="-.",
               linewidth=2, label=f"Determinístico: {deterministic_downtime:.1f}")

    ax.set_xlabel("Downtime Total (semanas-aeronave)", fontsize=11)
    ax.set_ylabel("Densidade", fontsize=11)
    ax.set_title("Distribuição do Downtime - Monte Carlo", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Histograma MC salvo em: {save_path}")


def plot_hangar_occupancy(
    fleet: List[Aircraft],
    result: ScheduleResult,
    save_path: str = "results/hangar_occupancy.png",
):
    """Gera gráfico de ocupação do hangar ao longo do tempo."""
    D = SB_DURATION_CEIL
    occupancy = np.zeros(HORIZON_WEEKS + 1)

    # SBs
    for ac_idx, sb_start in result.sb_schedule.items():
        for t in range(sb_start, min(sb_start + D, HORIZON_WEEKS + 1)):
            occupancy[t] += 1

    # Inspeções standalone
    for (ac_idx, milestone, week, dur) in result.standalone_inspections:
        dur_ceil = max(1, int(np.ceil(dur)))
        for t in range(week, min(week + dur_ceil, HORIZON_WEEKS + 1)):
            occupancy[t] += 1

    fig, ax = plt.subplots(figsize=(16, 5))

    weeks = list(range(1, HORIZON_WEEKS + 1))
    occ = [occupancy[t] for t in weeks]

    ax.fill_between(weeks, occ, alpha=0.6, color="#3498DB", step="mid")
    ax.step(weeks, occ, where="mid", color="#2C3E50", linewidth=1)

    # Capacidade máxima
    ax.axhline(y=HANGAR_CAPACITY, color="red", linestyle="--",
               linewidth=2, label=f"Capacidade máx. ({HANGAR_CAPACITY})")

    # 2026/2027
    ax.axvline(x=WEEKS_2026 + 0.5, color="black", linestyle="--",
               linewidth=1, alpha=0.5)

    ax.set_xlabel("Semana", fontsize=11)
    ax.set_ylabel("Aeronaves no hangar", fontsize=11)
    ax.set_title("Ocupação do Hangar", fontsize=13, fontweight="bold")
    ax.set_ylim(0, HANGAR_CAPACITY + 1)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Ocupação do hangar salva em: {save_path}")


def plot_fh_weekly_allocation(
    fleet: List[Aircraft],
    result: ScheduleResult,
    save_path: str = "results/fh_weekly_allocation.png",
):
    """Gera gráfico de alocação semanal de FH (stacked area)."""
    fig, ax = plt.subplots(figsize=(16, 6))

    weeks = list(range(1, HORIZON_WEEKS + 1))
    fh_data = {}
    for ac in fleet:
        fh_data[ac.index] = [
            result.fh_allocation.get((ac.index, t), 0.0) for t in weeks
        ]

    # Stacked area
    colors_list = plt.cm.tab10(np.linspace(0, 1, len(fleet)))
    bottom = np.zeros(len(weeks))
    for ac in fleet:
        values = np.array(fh_data[ac.index])
        ax.fill_between(weeks, bottom, bottom + values,
                        alpha=0.7, color=colors_list[ac.index], label=ac.id)
        bottom += values

    # Linha de meta semanal
    fh_rate_2026 = FH_TARGET_2026 / WEEKS_2026
    fh_rate_2027 = FH_TARGET_2027 / (HORIZON_WEEKS - WEEKS_2026)
    ax.axhline(y=fh_rate_2026, color="red", linestyle=":", alpha=0.5,
               xmin=0, xmax=WEEKS_2026 / HORIZON_WEEKS)
    ax.axhline(y=fh_rate_2027, color="red", linestyle=":", alpha=0.5,
               xmin=WEEKS_2026 / HORIZON_WEEKS, xmax=1)

    ax.axvline(x=WEEKS_2026 + 0.5, color="black", linestyle="--",
               linewidth=1, alpha=0.5)

    ax.set_xlabel("Semana", fontsize=11)
    ax.set_ylabel("FH / semana (frota total)", fontsize=11)
    ax.set_title("Alocação Semanal de Horas de Voo", fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, ncol=5)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Alocação FH semanal salva em: {save_path}")


def generate_all_plots(
    fleet: List[Aircraft],
    result: ScheduleResult,
    mc_results: Optional[MonteCarloResults] = None,
    output_dir: str = "results",
):
    """Gera todos os gráficos."""
    print("\n--- Gerando Visualizações ---")

    plot_gantt(fleet, result, save_path=f"{output_dir}/gantt_chart.png")
    plot_fh_profiles(fleet, result, save_path=f"{output_dir}/fh_profiles.png")
    plot_hangar_occupancy(fleet, result, save_path=f"{output_dir}/hangar_occupancy.png")
    plot_fh_weekly_allocation(fleet, result, save_path=f"{output_dir}/fh_weekly_allocation.png")

    if mc_results:
        plot_monte_carlo_histogram(
            mc_results,
            deterministic_downtime=result.total_downtime_weeks,
            save_path=f"{output_dir}/monte_carlo_histogram.png",
        )
