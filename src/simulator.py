"""
Fleet Downtime Minimizer - Monte Carlo Simulator
MPP30 Manutenção - ITA 2026

Simulação estocástica para validar o schedule ótimo do MILP.
Modela durações estocásticas (distribuição triangular) e
falhas operacionais inesperadas (processo de Poisson).
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np
from scipy import stats

from src.config import (
    HORIZON_WEEKS, WEEKS_2026, T_2026, T_2027, T_ALL,
    FH_TARGET_2026, FH_TARGET_2027, HANGAR_CAPACITY, FH_MAX_WEEK,
    SB_DURATION_CEIL, SB_DURATION_WEEKS_TRIANG, SB_EXPECTED_WEEKS,
    INSP100_DURATION_HOURS, INSP200_DURATION_HOURS, INSP400_DURATION_HOURS,
    HOURS_PER_WEEK, FAILURE_RATE, REPAIR_DURATION_WEEKS,
    MC_N_SIMULATIONS, MC_RANDOM_SEED, AIRCRAFT_DATA,
)
from src.models import (
    Aircraft, Inspection, ScheduleResult, build_fleet,
    get_inspection_level, compute_effective_window, compute_future_inspections,
)


@dataclass
class SimulationMetrics:
    """Métricas de uma rodada de simulação."""
    total_downtime: float = 0.0
    sb_downtime: float = 0.0
    insp_standalone_downtime: float = 0.0
    insp_packaged_savings: float = 0.0
    failure_downtime: float = 0.0
    constraint_violations: int = 0
    fh_2026: float = 0.0
    fh_2027: float = 0.0
    hangar_overflow_weeks: int = 0


@dataclass
class MonteCarloResults:
    """Resultados consolidados da simulação Monte Carlo."""
    n_simulations: int = 0
    metrics: List[SimulationMetrics] = field(default_factory=list)

    # Estatísticas do downtime total
    mean_downtime: float = 0.0
    std_downtime: float = 0.0
    p5_downtime: float = 0.0
    p25_downtime: float = 0.0
    p50_downtime: float = 0.0
    p75_downtime: float = 0.0
    p95_downtime: float = 0.0
    min_downtime: float = 0.0
    max_downtime: float = 0.0

    # Probabilidade de violação
    prob_constraint_violation: float = 0.0
    prob_hangar_overflow: float = 0.0

    # Falhas
    mean_failure_downtime: float = 0.0
    mean_n_failures: float = 0.0

    def compute_statistics(self):
        """Computa estatísticas a partir das métricas individuais."""
        downtimes = [m.total_downtime for m in self.metrics]
        self.mean_downtime = np.mean(downtimes)
        self.std_downtime = np.std(downtimes)
        self.p5_downtime = np.percentile(downtimes, 5)
        self.p25_downtime = np.percentile(downtimes, 25)
        self.p50_downtime = np.percentile(downtimes, 50)
        self.p75_downtime = np.percentile(downtimes, 75)
        self.p95_downtime = np.percentile(downtimes, 95)
        self.min_downtime = np.min(downtimes)
        self.max_downtime = np.max(downtimes)
        self.prob_constraint_violation = np.mean([
            1 if m.constraint_violations > 0 else 0 for m in self.metrics
        ])
        self.prob_hangar_overflow = np.mean([
            1 if m.hangar_overflow_weeks > 0 else 0 for m in self.metrics
        ])
        self.mean_failure_downtime = np.mean([m.failure_downtime for m in self.metrics])


def sample_sb_duration(rng: np.random.Generator) -> float:
    """Amostra duração do SB da distribuição triangular (em semanas)."""
    a, c, b = SB_DURATION_WEEKS_TRIANG  # min, moda, max
    return float(rng.triangular(a, c, b))


def sample_insp_duration(level: int, rng: np.random.Generator) -> float:
    """Amostra duração de inspeção da distribuição triangular (em semanas)."""
    if level == 100:
        a, c, b = INSP100_DURATION_HOURS
    elif level == 200:
        a, c, b = INSP200_DURATION_HOURS
    else:
        a, c, b = INSP400_DURATION_HOURS
    hours = float(rng.triangular(a, c, b))
    return hours / HOURS_PER_WEEK


def sample_repair_duration(rng: np.random.Generator) -> float:
    """Amostra duração de reparo corretivo (em semanas)."""
    a, c, b = REPAIR_DURATION_WEEKS
    return float(rng.triangular(a, c, b))


def simulate_schedule(
    fleet: List[Aircraft],
    schedule: ScheduleResult,
    rng: np.random.Generator,
    with_failures: bool = True,
) -> SimulationMetrics:
    """Simula o schedule com durações estocásticas e falhas.

    Avança semana a semana, rastreando:
    - Ocupação do hangar (SBs + inspeções + reparos)
    - Acúmulo de FH por aeronave
    - Inspeções devidas e realizadas
    - Falhas aleatórias

    Args:
        fleet: Lista de aeronaves
        schedule: Schedule determinístico do MILP (SB start weeks, FH allocation)
        rng: Gerador de números aleatórios
        with_failures: Se True, inclui falhas operacionais

    Returns:
        SimulationMetrics com resultados da simulação
    """
    metrics = SimulationMetrics()
    n = len(fleet)
    packaged_set = set(schedule.packaged_inspections)

    # Estado por aeronave
    fh = [ac.fh0 for ac in fleet]           # FH acumuladas
    in_maintenance = [False] * n             # Em manutenção?
    maint_end_week = [0.0] * n              # Semana (fracionária) de fim da manutenção
    maint_type = [""] * n                    # Tipo de manutenção atual

    # SB: amostrar durações
    sb_durations = {}
    for ac in fleet:
        if ac.needs_sb and ac.index in schedule.sb_schedule:
            sb_durations[ac.index] = sample_sb_duration(rng)

    # Rastrear inspeções pendentes por aeronave
    pending_inspections: Dict[int, List[Inspection]] = {}
    for ac in fleet:
        pending_inspections[ac.index] = list(ac.future_inspections)

    # Fila de espera para hangar
    hangar_queue: List[Tuple[int, str, float]] = []  # (ac_index, type, duration)

    # Simulação semana a semana
    for t in range(1, HORIZON_WEEKS + 1):
        hangar_count = sum(1 for m in in_maintenance if m)

        # 1. Verificar fins de manutenção
        for i in range(n):
            if in_maintenance[i] and t > maint_end_week[i]:
                in_maintenance[i] = False
                maint_type[i] = ""
                hangar_count -= 1

        # 2. Iniciar SBs programados
        for ac in fleet:
            if not ac.needs_sb:
                continue
            if ac.index not in schedule.sb_schedule:
                continue
            sb_week = schedule.sb_schedule[ac.index]
            if t == sb_week and not in_maintenance[ac.index]:
                if hangar_count < HANGAR_CAPACITY:
                    duration = sb_durations.get(ac.index, SB_EXPECTED_WEEKS)
                    in_maintenance[ac.index] = True
                    maint_end_week[ac.index] = t + duration - 1
                    maint_type[ac.index] = "SB"
                    metrics.sb_downtime += duration
                    hangar_count += 1

                    # Verificar inspeções empacotadas
                    still_pending = []
                    for insp in pending_inspections[ac.index]:
                        if (ac.index, insp.milestone) in packaged_set:
                            if insp.window_low <= fh[ac.index] <= insp.window_high:
                                insp_dur = sample_insp_duration(insp.level, rng)
                                # Empacotado: não adiciona downtime separado
                                metrics.insp_packaged_savings += insp_dur
                                continue
                        still_pending.append(insp)
                    pending_inspections[ac.index] = still_pending
                else:
                    hangar_queue.append((ac.index, "SB", sb_durations.get(ac.index, SB_EXPECTED_WEEKS)))
                    metrics.hangar_overflow_weeks += 1

        # 3. Processar fila de espera
        new_queue = []
        for (qi, qtype, qdur) in hangar_queue:
            if not in_maintenance[qi] and hangar_count < HANGAR_CAPACITY:
                in_maintenance[qi] = True
                maint_end_week[qi] = t + qdur - 1
                maint_type[qi] = qtype
                if qtype == "SB":
                    metrics.sb_downtime += qdur
                elif qtype == "REPAIR":
                    metrics.failure_downtime += qdur
                else:
                    metrics.insp_standalone_downtime += qdur
                hangar_count += 1
            else:
                new_queue.append((qi, qtype, qdur))
        hangar_queue = new_queue

        # 4. Alocar FH (usar alocação do MILP)
        for ac in fleet:
            if t < ac.available_week:
                continue
            if in_maintenance[ac.index]:
                continue  # Não voa durante manutenção

            fh_week = schedule.fh_allocation.get((ac.index, t), 0.0)
            fh[ac.index] += fh_week

            if t <= WEEKS_2026:
                metrics.fh_2026 += fh_week
            else:
                metrics.fh_2027 += fh_week

        # 5. Verificar inspeções devidas (standalone)
        for ac in fleet:
            if in_maintenance[ac.index]:
                continue
            still_pending = []
            for insp in pending_inspections[ac.index]:
                if (ac.index, insp.milestone) in packaged_set:
                    still_pending.append(insp)
                    continue

                if fh[ac.index] >= insp.window_low:
                    if fh[ac.index] <= insp.window_high:
                        # Dentro da janela → agendar inspeção
                        insp_dur = sample_insp_duration(insp.level, rng)
                        if hangar_count < HANGAR_CAPACITY and not in_maintenance[ac.index]:
                            in_maintenance[ac.index] = True
                            maint_end_week[ac.index] = t + insp_dur - 1
                            maint_type[ac.index] = f"INSP{insp.level}"
                            metrics.insp_standalone_downtime += insp_dur
                            hangar_count += 1
                        else:
                            hangar_queue.append((ac.index, f"INSP{insp.level}", insp_dur))
                        continue
                    else:
                        # Ultrapassou a janela sem inspeção → violação
                        metrics.constraint_violations += 1
                        insp_dur = sample_insp_duration(insp.level, rng)
                        if hangar_count < HANGAR_CAPACITY and not in_maintenance[ac.index]:
                            in_maintenance[ac.index] = True
                            maint_end_week[ac.index] = t + insp_dur - 1
                            maint_type[ac.index] = f"INSP{insp.level}"
                            metrics.insp_standalone_downtime += insp_dur
                            hangar_count += 1
                        else:
                            hangar_queue.append((ac.index, f"INSP{insp.level}", insp_dur))
                        continue

                still_pending.append(insp)
            pending_inspections[ac.index] = still_pending

        # 6. Falhas operacionais (Poisson)
        if with_failures:
            for ac in fleet:
                if t < ac.available_week:
                    continue
                if in_maintenance[ac.index]:
                    continue
                if rng.random() < FAILURE_RATE:
                    repair_dur = sample_repair_duration(rng)
                    if hangar_count < HANGAR_CAPACITY:
                        in_maintenance[ac.index] = True
                        maint_end_week[ac.index] = t + repair_dur - 1
                        maint_type[ac.index] = "REPAIR"
                        metrics.failure_downtime += repair_dur
                        hangar_count += 1
                    else:
                        hangar_queue.append((ac.index, "REPAIR", repair_dur))
                        metrics.hangar_overflow_weeks += 1

    # Total downtime
    metrics.total_downtime = (
        metrics.sb_downtime
        + metrics.insp_standalone_downtime
        + metrics.failure_downtime
    )

    return metrics


def run_monte_carlo(
    fleet: List[Aircraft],
    schedule: ScheduleResult,
    n_simulations: int = MC_N_SIMULATIONS,
    seed: int = MC_RANDOM_SEED,
    with_failures: bool = True,
    verbose: bool = True,
) -> MonteCarloResults:
    """Executa simulação Monte Carlo.

    Args:
        fleet: Lista de aeronaves
        schedule: Schedule determinístico do MILP
        n_simulations: Número de simulações
        seed: Semente aleatória
        with_failures: Se True, inclui falhas operacionais
        verbose: Se True, imprime progresso

    Returns:
        MonteCarloResults com estatísticas
    """
    rng = np.random.default_rng(seed)
    results = MonteCarloResults(n_simulations=n_simulations)

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"SIMULAÇÃO MONTE CARLO ({n_simulations} iterações)")
        print(f"Falhas operacionais: {'Sim' if with_failures else 'Não'}")
        print(f"{'=' * 60}")

    for k in range(n_simulations):
        if verbose and (k + 1) % 200 == 0:
            print(f"  Iteração {k + 1}/{n_simulations}...")

        metrics = simulate_schedule(fleet, schedule, rng, with_failures)
        results.metrics.append(metrics)

    results.compute_statistics()

    if verbose:
        print_monte_carlo_results(results)

    return results


def print_monte_carlo_results(results: MonteCarloResults):
    """Imprime resultados da simulação Monte Carlo."""
    print(f"\n--- Resultados Monte Carlo ({results.n_simulations} simulações) ---")
    print(f"\nDowntime Total (semanas-aeronave):")
    print(f"  Média:     {results.mean_downtime:.2f}")
    print(f"  Std:       {results.std_downtime:.2f}")
    print(f"  Mínimo:    {results.min_downtime:.2f}")
    print(f"  P5:        {results.p5_downtime:.2f}")
    print(f"  P25:       {results.p25_downtime:.2f}")
    print(f"  Mediana:   {results.p50_downtime:.2f}")
    print(f"  P75:       {results.p75_downtime:.2f}")
    print(f"  P95:       {results.p95_downtime:.2f}")
    print(f"  Máximo:    {results.max_downtime:.2f}")

    print(f"\nRobustez:")
    print(f"  P(violação de constraints): {results.prob_constraint_violation:.1%}")
    print(f"  P(overflow do hangar):      {results.prob_hangar_overflow:.1%}")

    print(f"\nFalhas Operacionais:")
    print(f"  Downtime médio por falhas: {results.mean_failure_downtime:.2f} semanas")

    print(f"\nComponentes do downtime médio:")
    mean_sb = np.mean([m.sb_downtime for m in results.metrics])
    mean_insp = np.mean([m.insp_standalone_downtime for m in results.metrics])
    mean_pkg = np.mean([m.insp_packaged_savings for m in results.metrics])
    mean_fail = np.mean([m.failure_downtime for m in results.metrics])
    print(f"  SB:                   {mean_sb:.2f}")
    print(f"  Inspeções standalone: {mean_insp:.2f}")
    print(f"  Empacotamento (eco):  {mean_pkg:.2f}")
    print(f"  Falhas operacionais:  {mean_fail:.2f}")
