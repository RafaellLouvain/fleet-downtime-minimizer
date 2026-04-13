"""
Fleet Downtime Minimizer - MILP Optimizer
MPP30 Manutenção - ITA 2026

Formulação MILP usando PuLP para otimizar o scheduling de SBs
e a alocação semanal de horas de voo, maximizando o empacotamento
de inspeções dentro dos períodos de SB.

Otimizações vs. formulação naïve:
  - sb_start criado apenas para semanas pares (reduz binários ~50%)
  - big-M específico por aeronave/inspeção (LP relaxation mais apertada)
  - R7 (empacotamento) apenas para semanas onde FH pode estar na janela
  - Limite de tempo de 300s
"""

import math
from typing import List, Dict, Tuple
import pulp

from src.config import (
    HORIZON_WEEKS, WEEKS_2026, T_2026, T_2027, T_ALL,
    FH_TARGET_2026, FH_TARGET_2027, HANGAR_CAPACITY, FH_MAX_WEEK,
    SB_DURATION_CEIL, SB_EXPECTED_WEEKS, AIRCRAFT_DATA,
)
from src.models import (
    Aircraft, Inspection, ScheduleResult,
    build_fleet, compute_future_inspections, get_inspection_level,
    get_inspection_duration,
)


def _compute_big_m(ac: Aircraft) -> float:
    """Big-M específico por aeronave: FH máximo possível no horizonte."""
    return ac.fh0 + FH_MAX_WEEK * HORIZON_WEEKS + 10


def _feasible_sb_weeks(ac: Aircraft, D: int, step: int = 2) -> List[int]:
    """Retorna semanas factíveis para início de SB.

    Filtra por: disponibilidade, horizonte, e passo (a cada 'step' semanas).
    """
    weeks = []
    for t in range(ac.available_week, HORIZON_WEEKS - D + 2):
        if (t - ac.available_week) % step == 0:
            weeks.append(t)
    # Garantir que a última semana factível esteja incluída
    last = HORIZON_WEEKS - D + 1
    if last not in weeks and last >= ac.available_week:
        weeks.append(last)
    return sorted(weeks)


def _can_reach_window(ac: Aircraft, t: int, window_low: int, window_high: int) -> bool:
    """Verifica se a aeronave PODE ter FH dentro da janela na semana t.

    Min FH na semana t: fh0 (não voou nada)
    Max FH na semana t: fh0 + FH_MAX_WEEK * t
    """
    min_fh = ac.fh0
    max_fh = ac.fh0 + FH_MAX_WEEK * t
    return min_fh <= window_high and max_fh >= window_low


def solve_milp(fleet: List[Aircraft], verbose: bool = True) -> ScheduleResult:
    """Resolve o MILP para encontrar o scheduling ótimo.

    Variáveis de decisão:
        sb_start[i][t]  ∈ {0,1} : aeronave i inicia SB na semana t
        x[i][t]         ≥ 0     : FH da aeronave i na semana t
        pkg[i][j]       ∈ {0,1} : inspeção j da aeronave i é empacotada no SB

    Objetivo:
        Maximizar o downtime total empacotado (= minimizar downtime standalone)
    """
    D = SB_DURATION_CEIL
    sb_aircraft = [ac for ac in fleet if ac.needs_sb]
    all_aircraft = fleet

    # -----------------------------------------------------------------
    # 1. Pre-computar inspeções empacotáveis para cada aeronave
    # -----------------------------------------------------------------
    pkg_inspections: Dict[int, List[Inspection]] = {}
    for ac in sb_aircraft:
        # Limitar inspeções a FH0+500: suficiente para capturar packaging relevante
        # e evitar variáveis pkg para milestones impossíveis de alcançar antes do SB
        max_fh = min(ac.fh0 + 500, ac.fh0 + FH_MAX_WEEK * HORIZON_WEEKS)
        inspections = compute_future_inspections(int(ac.fh0), int(max_fh))
        pkg_inspections[ac.index] = inspections

    # Semanas factíveis para SB de cada aeronave
    feasible_weeks: Dict[int, List[int]] = {}
    for ac in sb_aircraft:
        feasible_weeks[ac.index] = _feasible_sb_weeks(ac, D, step=2)

    # -----------------------------------------------------------------
    # 2. Criar modelo PuLP
    # -----------------------------------------------------------------
    model = pulp.LpProblem("FleetDowntimeMinimizer", pulp.LpMaximize)

    # -----------------------------------------------------------------
    # 3. Variáveis de decisão
    # -----------------------------------------------------------------

    # sb_start[i][t]: aeronave i inicia SB na semana t (apenas semanas factíveis)
    sb_start = {}
    for ac in sb_aircraft:
        for t in feasible_weeks[ac.index]:
            sb_start[ac.index, t] = pulp.LpVariable(
                f"sb_{ac.index}_{t}", cat="Binary"
            )

    # x[i][t]: FH da aeronave i na semana t
    x = {}
    for ac in all_aircraft:
        for t in T_ALL:
            x[ac.index, t] = pulp.LpVariable(
                f"x_{ac.index}_{t}", lowBound=0, upBound=FH_MAX_WEEK
            )

    # pkg[i][j]: inspeção com milestone j empacotada no SB
    pkg = {}
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            pkg[ac.index, insp.milestone] = pulp.LpVariable(
                f"pkg_{ac.index}_{insp.milestone}", cat="Binary"
            )

    # -----------------------------------------------------------------
    # 4. Expressões derivadas
    # -----------------------------------------------------------------

    # in_sb[i][t]: aeronave i está em SB na semana t
    in_sb = {}
    for ac in sb_aircraft:
        for t in T_ALL:
            terms = []
            for tau in range(max(1, t - D + 1), t + 1):
                if (ac.index, tau) in sb_start:
                    terms.append(sb_start[ac.index, tau])
            in_sb[ac.index, t] = pulp.lpSum(terms) if terms else 0

    # cum_fh[i][t]: FH acumuladas da aeronave i ao final da semana t
    # (expressão linear, não variável separada)
    def get_cum_fh(i, t):
        ac = fleet[i]
        return ac.fh0 + pulp.lpSum(x[i, tau] for tau in range(1, t + 1))

    # -----------------------------------------------------------------
    # 5. Função Objetivo
    # -----------------------------------------------------------------
    objective_terms = []
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) in pkg:
                objective_terms.append(
                    insp.duration_weeks * pkg[ac.index, insp.milestone]
                )

    model += pulp.lpSum(objective_terms), "MaxPackagedDowntime"

    # -----------------------------------------------------------------
    # 6. Restrições
    # -----------------------------------------------------------------

    # R1. Exatamente um início de SB por aeronave
    for ac in sb_aircraft:
        model += (
            pulp.lpSum(sb_start[ac.index, t] for t in feasible_weeks[ac.index]) == 1,
            f"R1_one_sb_{ac.index}"
        )

    # R2. Não voar durante SB
    for ac in sb_aircraft:
        for t in T_ALL:
            val = in_sb.get((ac.index, t), 0)
            if isinstance(val, (int, float)):
                continue
            model += (
                x[ac.index, t] <= FH_MAX_WEEK * (1 - val),
                f"R2_{ac.index}_{t}"
            )

    # R3. Capacidade do hangar (SBs; inspeções curtas tratadas em pós-processamento)
    for t in T_ALL:
        hangar_terms = []
        for ac in sb_aircraft:
            val = in_sb.get((ac.index, t), 0)
            if not isinstance(val, (int, float)):
                hangar_terms.append(val)
        if hangar_terms:
            model += (
                pulp.lpSum(hangar_terms) <= HANGAR_CAPACITY,
                f"R3_{t}"
            )

    # R4. Esforço aéreo (igualdade)
    model += (
        pulp.lpSum(x[ac.index, t] for ac in all_aircraft for t in T_2026) == FH_TARGET_2026,
        "R4_2026"
    )
    model += (
        pulp.lpSum(x[ac.index, t] for ac in all_aircraft for t in T_2027) == FH_TARGET_2027,
        "R4_2027"
    )

    # R5. Disponibilidade
    for ac in all_aircraft:
        for t in T_ALL:
            if t < ac.available_week:
                model += (x[ac.index, t] == 0, f"R5_{ac.index}_{t}")

    # R6. FH na entrada do SB ≤ 410 (SB antes ou durante Insp400)
    for ac in sb_aircraft:
        insp400_upper = 410
        for insp in pkg_inspections[ac.index]:
            if insp.level == 400:
                insp400_upper = insp.window_high
                break
        M_r6 = _compute_big_m(ac)
        for t in feasible_weeks[ac.index]:
            model += (
                get_cum_fh(ac.index, t) <= insp400_upper + M_r6 * (1 - sb_start[ac.index, t]),
                f"R6_{ac.index}_{t}"
            )

    # R7. Empacotamento válido (APENAS para semanas onde FH pode estar na janela)
    # R8. Linking: pkg[i][j] só pode ser 1 se SB inicia numa semana reachable
    n_r7 = 0
    for ac in sb_aircraft:
        M_ac = _compute_big_m(ac)
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) not in pkg:
                continue
            reachable_weeks = []
            for t in feasible_weeks[ac.index]:
                if not _can_reach_window(ac, t, insp.window_low, insp.window_high):
                    continue
                reachable_weeks.append(t)
                cum = get_cum_fh(ac.index, t)
                model += (
                    cum >= insp.window_low - M_ac * (2 - sb_start[ac.index, t] - pkg[ac.index, insp.milestone]),
                    f"R7L_{ac.index}_{insp.milestone}_{t}"
                )
                model += (
                    cum <= insp.window_high + M_ac * (2 - sb_start[ac.index, t] - pkg[ac.index, insp.milestone]),
                    f"R7H_{ac.index}_{insp.milestone}_{t}"
                )
                n_r7 += 2

            # R8: pkg só pode ser 1 se SB inicia numa semana onde o FH pode
            # estar na janela da inspeção (linking constraint)
            if reachable_weeks:
                model += (
                    pkg[ac.index, insp.milestone] <= pulp.lpSum(
                        sb_start[ac.index, t] for t in reachable_weeks
                    ),
                    f"R8_{ac.index}_{insp.milestone}"
                )
            else:
                # Nenhuma semana factível pode atingir a janela → impossível empacotar
                model += (
                    pkg[ac.index, insp.milestone] == 0,
                    f"R8_impossible_{ac.index}_{insp.milestone}"
                )

    # -----------------------------------------------------------------
    # 7. Resolver
    # -----------------------------------------------------------------
    n_binary = sum(1 for v in model.variables() if v.cat == "Binary")
    n_cont = sum(1 for v in model.variables() if v.cat == "Continuous")

    if verbose:
        print("=" * 60)
        print("MILP - Fleet Downtime Minimizer")
        print("=" * 60)
        print(f"Variáveis: {n_binary} binárias + {n_cont} contínuas = {len(model.variables())}")
        print(f"Restrições: {len(model.constraints)} (R7: {n_r7})")
        print("Resolvendo (time limit: 300s)...")

    solver = pulp.PULP_CBC_CMD(msg=1 if verbose else 0, timeLimit=300)
    status = model.solve(solver)

    # Verificar gap
    obj_val = pulp.value(model.objective) if pulp.value(model.objective) else 0.0
    status_str = pulp.LpStatus[status]

    if verbose:
        print(f"Status: {status_str}")
        print(f"Objetivo (packaging savings): {obj_val:.3f} semanas")

    # -----------------------------------------------------------------
    # 8. Extrair resultados
    # -----------------------------------------------------------------
    result = ScheduleResult()
    result.solver_status = status_str
    result.objective_value = obj_val

    if status not in (pulp.constants.LpStatusOptimal,):
        print(f"AVISO: Status '{status_str}'. Usando melhor solução encontrada.")
        if obj_val == 0:
            return result

    # Extrair SB schedule
    for ac in sb_aircraft:
        for t in feasible_weeks[ac.index]:
            if (ac.index, t) in sb_start:
                if pulp.value(sb_start[ac.index, t]) > 0.5:
                    result.sb_schedule[ac.index] = t
                    break

    # Extrair FH allocation
    for ac in all_aircraft:
        for t in T_ALL:
            val = pulp.value(x[ac.index, t])
            if val and val > 0.001:
                result.fh_allocation[ac.index, t] = val

    # Extrair packaging
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) in pkg:
                if pulp.value(pkg[ac.index, insp.milestone]) > 0.5:
                    result.packaged_inspections.append((ac.index, insp.milestone))

    # Calcular FH na entrada do SB
    for ac in sb_aircraft:
        if ac.index in result.sb_schedule:
            t_start = result.sb_schedule[ac.index]
            fh_entry = ac.fh0
            for tau in range(1, t_start + 1):
                fh_entry += result.fh_allocation.get((ac.index, tau), 0.0)
            result.fh_at_sb_entry[ac.index] = fh_entry

    # Calcular downtime
    result.sb_downtime_weeks = len(sb_aircraft) * SB_DURATION_CEIL
    result.packaged_insp_savings_weeks = obj_val

    # Computar inspeções standalone
    result.standalone_inspections, result.standalone_insp_downtime_weeks = \
        _compute_standalone_inspections(fleet, result)

    result.total_downtime_weeks = (
        result.sb_downtime_weeks + result.standalone_insp_downtime_weeks
    )

    return result


def _compute_standalone_inspections(
    fleet: List[Aircraft], schedule: ScheduleResult
) -> Tuple[list, float]:
    """Computa inspeções standalone simulando o perfil de FH."""
    standalone = []
    total_downtime = 0.0
    D = SB_DURATION_CEIL
    packaged_set = set(schedule.packaged_inspections)

    for ac in fleet:
        fh = ac.fh0
        sb_start_week = schedule.sb_schedule.get(ac.index, None)
        sb_weeks = set()
        if sb_start_week:
            sb_weeks = set(range(sb_start_week, sb_start_week + D))

        pending_inspections = list(ac.future_inspections)

        for t in range(1, HORIZON_WEEKS + 1):
            if t < ac.available_week:
                continue
            if t in sb_weeks:
                continue

            fh += schedule.fh_allocation.get((ac.index, t), 0.0)

            still_pending = []
            for insp in pending_inspections:
                if (ac.index, insp.milestone) in packaged_set:
                    continue
                if fh >= insp.window_low:
                    standalone.append((ac.index, insp.milestone, t, insp.duration_weeks))
                    total_downtime += insp.duration_weeks
                    continue
                still_pending.append(insp)
            pending_inspections = still_pending

    return standalone, total_downtime


def print_schedule(fleet: List[Aircraft], result: ScheduleResult):
    """Imprime o schedule de forma legível."""
    D = SB_DURATION_CEIL

    print("\n" + "=" * 70)
    print("SCHEDULE ÓTIMO DE MANUTENÇÃO")
    print("=" * 70)

    print(f"\nStatus do solver: {result.solver_status}")
    print(f"Packaging savings: {result.packaged_insp_savings_weeks:.3f} semanas")

    print("\n--- Service Bulletins ---")
    print(f"{'Aeronave':<10} {'Início':<10} {'Fim':<10} {'FH Entrada':<12} {'Insps Empac.'}")
    print("-" * 65)

    sb_items = sorted(result.sb_schedule.items(), key=lambda x: x[1])
    for ac_idx, start_week in sb_items:
        ac = fleet[ac_idx]
        end_week = start_week + D - 1
        fh_entry = result.fh_at_sb_entry.get(ac_idx, ac.fh0)
        packaged = [m for (i, m) in result.packaged_inspections if i == ac_idx]
        pkg_str = ", ".join(f"Insp@{m}" for m in packaged) if packaged else "Nenhuma"
        print(f"{ac.id:<10} Sem {start_week:<6} Sem {end_week:<6} {fh_entry:<12.1f} {pkg_str}")

    print("\n--- Esforço Aéreo ---")
    fh_2026 = sum(
        result.fh_allocation.get((ac.index, t), 0.0)
        for ac in fleet for t in T_2026
    )
    fh_2027 = sum(
        result.fh_allocation.get((ac.index, t), 0.0)
        for ac in fleet for t in T_2027
    )
    print(f"2026: {fh_2026:.1f} FH (meta: {FH_TARGET_2026})")
    print(f"2027: {fh_2027:.1f} FH (meta: {FH_TARGET_2027})")
    print(f"Total: {fh_2026 + fh_2027:.1f} FH")

    print("\n--- Downtime ---")
    print(f"SB total:                    {result.sb_downtime_weeks:.1f} semanas-aeronave")
    print(f"Inspeções standalone:        {result.standalone_insp_downtime_weeks:.1f} semanas-aeronave")
    print(f"Inspeções empacotadas (eco): {result.packaged_insp_savings_weeks:.1f} semanas-aeronave")
    print(f"DOWNTIME TOTAL:              {result.total_downtime_weeks:.1f} semanas-aeronave")
    print("=" * 70)
