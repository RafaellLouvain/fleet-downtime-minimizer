"""
Fleet Downtime Minimizer - MILP Optimizer
MPP30 Manutenção - ITA 2026

Formulação MILP (PuLP/CBC) que decide simultaneamente:
  - quando cada aeronave inicia o Service Bulletin
  - como distribuir as horas de voo (FH) semanais
  - quais inspeções de 400 FH são empacotadas dentro do SB

A função objetivo maximiza o downtime de inspeções empacotadas (que é
equivalente a minimizar o downtime total, já que o downtime do SB é
fixo: 8 aeronaves × 16 semanas).

Pequenas otimizações de modelagem para reduzir o tempo do CBC:
  - SBs só podem iniciar em semanas pares (passo=2 → ~50% menos binários)
  - Big-M específico por aeronave (relaxação LP mais apertada)
  - Restrições R7 só ativas em semanas onde o FH pode atingir a janela
"""

import math
from typing import List, Dict, Tuple
import pulp

from src.config import (
    HORIZON_WEEKS,
    T_2026,
    T_2027,
    T_ALL,
    FH_TARGET_2026,
    FH_TARGET_2027,
    HANGAR_CAPACITY,
    FH_MAX_WEEK,
    SB_DURATION_CEIL,
)
from src.models import (
    Aircraft,
    Inspection,
    ScheduleResult,
    compute_future_inspections,
)


def _compute_max_possible_fh(ac: Aircraft) -> float:
    """Big-M específico por aeronave: FH máximo que ela pode acumular no horizonte.

    Usado nas restrições R6/R7. Um Big-M apertado por aeronave deixa a
    relaxação LP mais próxima do MILP inteiro, acelerando o CBC.
    """
    return ac.fh0 + FH_MAX_WEEK * HORIZON_WEEKS + 10


def _feasible_sb_weeks(ac: Aircraft, D: int, step: int = 2) -> List[int]:
    """Semanas em que o SB pode iniciar (uma binária por semana).

    Restringe a:
      - t >= available_week  (aeronave já entregue)
      - t + D - 1 <= HORIZON_WEEKS  (SB cabe no horizonte)
      - t no passo `step`  (passo=2 corta ~50% das binárias sem perda prática
        de qualidade — o solver pode escolher entre semanas pares vizinhas)
    A última semana factível é incluída explicitamente caso o passo a pule.
    """
    weeks = []
    for t in range(ac.available_week, HORIZON_WEEKS - D + 2):
        if (t - ac.available_week) % step == 0:
            weeks.append(t)
    last = HORIZON_WEEKS - D + 1
    if last not in weeks and last >= ac.available_week:
        weeks.append(last)
    return sorted(weeks)


def _can_reach_window(ac: Aircraft, t: int, window_low: int, window_high: int) -> bool:
    """True se o FH da aeronave na semana t PODE estar em [window_low, window_high].

    Como FH(t) ∈ [fh0, fh0 + FH_MAX_WEEK*t], basta checar interseção. Usado
    para podar restrições R7 que jamais ficariam ativas, encolhendo o modelo.
    """
    min_fh = ac.fh0
    max_fh = ac.fh0 + FH_MAX_WEEK * t
    return min_fh <= window_high and max_fh >= window_low


def solve_milp(fleet: List[Aircraft], verbose: bool = True) -> ScheduleResult:
    """Resolve o MILP e retorna o ScheduleResult já com inspeções pós-processadas.

    Variáveis de decisão do MILP:
        does_ac_start_sb_at_week[i, t]  ∈ {0,1}  — aeronave i inicia SB na semana t
        fh_flown[i, t]                  ≥ 0      — FH voadas pela aeronave i na semana t
        is_insp_packaged[i, milestone]  ∈ {0,1}  — inspeção empacotada dentro do SB

    Objetivo: maximizar a soma das durações das inspeções empacotadas
    (equivalente a minimizar o downtime total, dado que o SB é fixo).
    Inspeções não empacotadas são agendadas em pós-processamento.
    """
    D = SB_DURATION_CEIL
    sb_aircraft = [ac for ac in fleet if ac.needs_sb]
    all_aircraft = fleet

    # -----------------------------------------------------------------
    # 1. Inspeções candidatas ao empacotamento (entram como variáveis pkg)
    # -----------------------------------------------------------------
    # Restringimos ao nível 400: é a inspeção longa (~1.4 sem) que justifica
    # ocupar uma binária no MILP. Insp100/200 são curtas e ficam para o
    # pós-processamento oportunístico — deixá-las no MILP poderia distorcer
    # o objetivo (empacotar uma Insp100 cedo "vale" pouco mas pode ser
    # escolhida em detrimento da Insp400 que daria muito mais economia).
    pkg_inspections: Dict[int, List[Inspection]] = {}
    for ac in sb_aircraft:
        max_fh = min(ac.fh0 + 400, ac.fh0 + FH_MAX_WEEK * HORIZON_WEEKS)
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

    # does_ac_start_sb_at_week[i][t]: aeronave i inicia SB na semana t (apenas semanas factíveis)
    does_ac_start_sb_at_week = {}
    for ac in sb_aircraft:
        for t in feasible_weeks[ac.index]:
            does_ac_start_sb_at_week[ac.index, t] = pulp.LpVariable(
                f"sb_{ac.index}_{t}", cat="Binary"
            )

    # fh_flown[i, t]: FH voadas pela aeronave i na semana t
    fh_flown = {}
    for ac in all_aircraft:
        for t in T_ALL:
            fh_flown[ac.index, t] = pulp.LpVariable(
                f"fh_{ac.index}_{t}", lowBound=0, upBound=FH_MAX_WEEK
            )

    # is_insp_packaged[i, milestone]: inspeção com dado milestone é empacotada no SB da aeronave i
    is_insp_packaged = {}
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            is_insp_packaged[ac.index, insp.milestone] = pulp.LpVariable(
                f"pkg_{ac.index}_{insp.milestone}", cat="Binary"
            )

    # -----------------------------------------------------------------
    # 4. Expressões derivadas (estados, não decisões)
    # -----------------------------------------------------------------

    # is_ac_in_sb[i, t] = soma das binárias de início de SB nas D semanas
    # anteriores. Vale 1 sse a aeronave está dentro do período do SB na
    # semana t. Como exatamente uma binária é 1 (R1), o valor é 0 ou 1.
    is_ac_in_sb = {}
    for ac in sb_aircraft:
        for t in T_ALL:
            terms = [
                does_ac_start_sb_at_week[ac.index, tau]
                for tau in range(max(1, t - D + 1), t + 1)
                if (ac.index, tau) in does_ac_start_sb_at_week
            ]
            is_ac_in_sb[ac.index, t] = pulp.lpSum(terms) if terms else 0

    # cum_fh(i, t) = fh0_i + Σ_{tau=1..t} fh_flown[i, tau]
    # Construído sob demanda como expressão linear (não vira variável).
    def get_cum_fh(i, t):
        ac = fleet[i]
        return ac.fh0 + pulp.lpSum(fh_flown[i, tau] for tau in range(1, t + 1))

    # -----------------------------------------------------------------
    # 5. Função Objetivo
    # -----------------------------------------------------------------
    # Termo principal: soma das durações das inspeções empacotadas
    objective_terms = []
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) in is_insp_packaged:
                objective_terms.append(
                    insp.duration_weeks * is_insp_packaged[ac.index, insp.milestone]
                )

    # Tiebreaker: entre soluções com mesmo packaging, preferir SBs mais cedo.
    # Sem isso, o solver pode concentrar todos os SBs no fim do horizonte e
    # deixar ANV-09/10 (que não fazem SB) sem espaço para inspeções standalone.
    # epsilon = 1e-4 é pequeno o suficiente para não trocar uma Insp400
    # (~1.38 sem) por uma Insp100 (~0.29 sem), mas grande o suficiente para
    # ordenar SBs entre semanas vizinhas.
    epsilon = 1e-4
    early_sb_terms = [
        t * does_ac_start_sb_at_week[ac.index, t]
        for ac in sb_aircraft
        for t in feasible_weeks[ac.index]
    ]

    model += (
        pulp.lpSum(objective_terms) - epsilon * pulp.lpSum(early_sb_terms),
        "MaxPackagedDowntime",
    )

    # -----------------------------------------------------------------
    # 6. Restrições
    # -----------------------------------------------------------------

    # R1 — Exatamente um início de SB por aeronave: Σ_t sb[i,t] = 1
    for ac in sb_aircraft:
        model += (
            pulp.lpSum(
                does_ac_start_sb_at_week[ac.index, t] for t in feasible_weeks[ac.index]
            )
            == 1,
            f"R1_one_sb_{ac.index}",
        )

    # R2 — Não voar durante o SB: fh[i,t] <= FH_MAX_WEEK * (1 - is_ac_in_sb[i,t]).
    # Quando is_ac_in_sb=1, força fh<=0; caso contrário a binária é solta.
    for ac in sb_aircraft:
        for t in T_ALL:
            val = is_ac_in_sb.get((ac.index, t), 0)
            if isinstance(val, (int, float)):
                continue
            model += (
                fh_flown[ac.index, t] <= FH_MAX_WEEK * (1 - val),
                f"R2_{ac.index}_{t}",
            )

    # R3 — Capacidade do hangar: até HANGAR_CAPACITY SBs simultâneos por semana.
    # Inspeções curtas (~0.3-1.4 sem) são acomodadas no pós-processamento.
    for t in T_ALL:
        hangar_terms = []
        for ac in sb_aircraft:
            val = is_ac_in_sb.get((ac.index, t), 0)
            if not isinstance(val, (int, float)):
                hangar_terms.append(val)
        if hangar_terms:
            model += (pulp.lpSum(hangar_terms) <= HANGAR_CAPACITY, f"R3_{t}")

    # R4 — Esforço aéreo: somatório de FH por ano deve igualar a meta.
    model += (
        pulp.lpSum(fh_flown[ac.index, t] for ac in all_aircraft for t in T_2026)
        == FH_TARGET_2026,
        "R4_2026",
    )
    model += (
        pulp.lpSum(fh_flown[ac.index, t] for ac in all_aircraft for t in T_2027)
        == FH_TARGET_2027,
        "R4_2027",
    )

    # R5 — Disponibilidade: aeronave não voa antes de ser entregue.
    for ac in all_aircraft:
        for t in T_ALL:
            if t < ac.available_week:
                model += (fh_flown[ac.index, t] == 0, f"R5_{ac.index}_{t}")

    # R6 — SB deve terminar antes ou durante a janela da Insp400.
    # Quando sb[i,t] = 1, força cum_fh(i,t) <= 410. O big-M solta a restrição
    # nas semanas em que sb[i,t] = 0.
    for ac in sb_aircraft:
        insp400_upper = 410
        for insp in pkg_inspections[ac.index]:
            if insp.level == 400:
                insp400_upper = insp.window_high
                break
        max_possible_fh = _compute_max_possible_fh(ac)
        for t in feasible_weeks[ac.index]:
            model += (
                get_cum_fh(ac.index, t)
                <= insp400_upper
                + max_possible_fh * (1 - does_ac_start_sb_at_week[ac.index, t]),
                f"R6_{ac.index}_{t}",
            )

    # R7 — Janela de empacotamento (big-M duplo). Quando AMBAS sb[i,t]=1 e
    # pkg[i,j]=1, força window_low <= cum_fh(i,t) <= window_high. Caso
    # contrário (qualquer das duas = 0), o termo (2 - sb - pkg) >= 1 solta.
    # R8 — Linking: pkg[i,j] só pode ser 1 se houver alguma semana factível
    # de início de SB onde o FH possa atingir a janela da inspeção.
    n_r7 = 0
    for ac in sb_aircraft:
        max_possible_fh = _compute_max_possible_fh(ac)
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) not in is_insp_packaged:
                continue
            reachable_weeks = []
            for t in feasible_weeks[ac.index]:
                if not _can_reach_window(ac, t, insp.window_low, insp.window_high):
                    continue
                reachable_weeks.append(t)
                cum = get_cum_fh(ac.index, t)
                slack = (
                    2
                    - does_ac_start_sb_at_week[ac.index, t]
                    - is_insp_packaged[ac.index, insp.milestone]
                )
                model += (
                    cum >= insp.window_low - max_possible_fh * slack,
                    f"R7L_{ac.index}_{insp.milestone}_{t}",
                )
                model += (
                    cum <= insp.window_high + max_possible_fh * slack,
                    f"R7H_{ac.index}_{insp.milestone}_{t}",
                )
                n_r7 += 2

            if reachable_weeks:
                model += (
                    is_insp_packaged[ac.index, insp.milestone]
                    <= pulp.lpSum(
                        does_ac_start_sb_at_week[ac.index, t] for t in reachable_weeks
                    ),
                    f"R8_{ac.index}_{insp.milestone}",
                )
            else:
                model += (
                    is_insp_packaged[ac.index, insp.milestone] == 0,
                    f"R8_impossible_{ac.index}_{insp.milestone}",
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
        print(
            f"Variáveis: {n_binary} binárias + {n_cont} contínuas = {len(model.variables())}"
        )
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
            if (ac.index, t) in does_ac_start_sb_at_week:
                if pulp.value(does_ac_start_sb_at_week[ac.index, t]) > 0.5:
                    result.sb_schedule[ac.index] = t
                    break

    # Extrair FH allocation
    for ac in all_aircraft:
        for t in T_ALL:
            val = pulp.value(fh_flown[ac.index, t])
            if val and val > 0.001:
                result.fh_allocation[ac.index, t] = val

    # Extrair packaging
    for ac in sb_aircraft:
        for insp in pkg_inspections[ac.index]:
            if (ac.index, insp.milestone) in is_insp_packaged:
                if pulp.value(is_insp_packaged[ac.index, insp.milestone]) > 0.5:
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

    # Computar inspeções standalone (pode adicionar empacotamentos oportunísticos)
    result.standalone_inspections, result.standalone_insp_downtime_weeks = (
        _compute_standalone_inspections(fleet, result)
    )

    # Recalcular savings com base na lista final de packaged_inspections
    insp_by_milestone = {
        (ac.index, i.milestone): i for ac in fleet for i in ac.future_inspections
    }
    result.packaged_insp_savings_weeks = sum(
        insp_by_milestone[(ac_idx, m)].duration_weeks
        for (ac_idx, m) in result.packaged_inspections
        if (ac_idx, m) in insp_by_milestone
    )

    result.total_downtime_weeks = (
        result.sb_downtime_weeks + result.standalone_insp_downtime_weeks
    )

    return result


def _compute_standalone_inspections(
    fleet: List[Aircraft], schedule: ScheduleResult
) -> Tuple[list, float]:
    """Agenda as inspeções 100/200 (e quaisquer 400 não cobertas pelo MILP).

    O MILP decide só os SBs e a alocação de FH; aqui completamos o schedule
    com as inspeções periódicas, em três passos:

      1. Simula FH semana a semana de cada aeronave (FH congelado nas D
         semanas do SB) e registra a primeira semana em que cada inspeção
         entra na sua janela (`due_week`).
      2. Para cada inspeção pendente, em ordem cronológica, tenta
         EMPACOTAR oportunisticamente: se a aeronave faz SB e o FH na
         entrada do SB cai na janela da inspeção, ela é executada dentro
         do SB sem custo extra de hangar.
      3. Caso não dê para empacotar, agenda STANDALONE na primeira semana
         >= due_week em que (a) o hangar tem slot livre e (b) a própria
         aeronave não está em outro evento de manutenção.

    Mantém invariante de R3 (hangar <= HANGAR_CAPACITY) considerando SBs +
    standalones simultâneos.
    """
    standalone: list = []
    total_downtime = 0.0
    D = SB_DURATION_CEIL

    # Ocupação inicial do hangar: contabiliza apenas as semanas dos SBs.
    hangar_occupancy: dict[int, int] = {}
    sb_weeks_by_ac: dict[int, set[int]] = {}
    for ac in fleet:
        sb_start = schedule.sb_schedule.get(ac.index)
        if sb_start:
            weeks = set(range(sb_start, sb_start + D))
            sb_weeks_by_ac[ac.index] = weeks
            for t in weeks:
                hangar_occupancy[t] = hangar_occupancy.get(t, 0) + 1
        else:
            sb_weeks_by_ac[ac.index] = set()

    # Inspeções já marcadas como empacotadas pelo MILP (Insp400).
    packaged_set: set[tuple[int, int]] = set(schedule.packaged_inspections)

    # --- Passo 1: detectar a semana de vencimento de cada inspeção ---
    # Uma inspeção "vence" na primeira semana em que FH atinge window_low.
    inspection_events: list[tuple[int, int, Inspection]] = []
    for ac in fleet:
        fh = ac.fh0
        sb_weeks = sb_weeks_by_ac[ac.index]
        remaining = [
            i
            for i in ac.future_inspections
            if (ac.index, i.milestone) not in packaged_set
        ]
        remaining.sort(key=lambda insp: insp.milestone)
        idx = 0
        for t in range(1, HORIZON_WEEKS + 1):
            if t < ac.available_week:
                continue
            if t not in sb_weeks:
                fh += schedule.fh_allocation.get((ac.index, t), 0.0)
            # Pode haver várias inspeções vencendo na mesma semana se a
            # aeronave acumular muito FH (raro, mas tratado).
            while idx < len(remaining) and fh >= remaining[idx].window_low:
                inspection_events.append((t, ac.index, remaining[idx]))
                idx += 1

    # --- Passo 2 e 3: empacotamento oportunístico ou agendamento standalone ---
    inspection_events.sort(key=lambda ev: (ev[0], ev[1], ev[2].milestone))
    ac_busy_until: dict[int, int] = {}

    for due_week, ac_idx, insp in inspection_events:
        if (ac_idx, insp.milestone) in packaged_set:
            continue

        ac = fleet[ac_idx]
        sb_start = schedule.sb_schedule.get(ac_idx)

        # (a) Empacotamento oportunístico: o FH de entrada do SB cai na janela?
        if sb_start is not None:
            fh_at_sb = schedule.fh_at_sb_entry.get(ac_idx, ac.fh0)
            if insp.window_low <= fh_at_sb <= insp.window_high:
                packaged_set.add((ac_idx, insp.milestone))
                if (ac_idx, insp.milestone) not in schedule.packaged_inspections:
                    schedule.packaged_inspections.append((ac_idx, insp.milestone))
                continue

        # (b) Standalone: primeira semana >= due_week com slot e aeronave livre
        dur_weeks = max(1, math.ceil(insp.duration_weeks))
        start = max(due_week, ac_busy_until.get(ac_idx, 0) + 1)
        sb_weeks = sb_weeks_by_ac[ac_idx]
        scheduled = False
        while start + dur_weeks - 1 <= HORIZON_WEEKS:
            block = range(start, start + dur_weeks)
            if all(t not in sb_weeks for t in block) and all(
                hangar_occupancy.get(t, 0) < HANGAR_CAPACITY for t in block
            ):
                scheduled = True
                break
            start += 1

        if scheduled:
            for t in range(start, start + dur_weeks):
                hangar_occupancy[t] = hangar_occupancy.get(t, 0) + 1
            ac_busy_until[ac_idx] = start + dur_weeks - 1
            standalone.append((ac_idx, insp.milestone, start, insp.duration_weeks))
            total_downtime += insp.duration_weeks

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
    print(
        f"{'Aeronave':<10} {'Início':<10} {'Fim':<10} {'FH Entrada':<12} {'Insps Empac.'}"
    )
    print("-" * 65)

    sb_items = sorted(result.sb_schedule.items(), key=lambda x: x[1])
    for ac_idx, start_week in sb_items:
        ac = fleet[ac_idx]
        end_week = start_week + D - 1
        fh_entry = result.fh_at_sb_entry.get(ac_idx, ac.fh0)
        packaged = [m for (i, m) in result.packaged_inspections if i == ac_idx]
        pkg_str = ", ".join(f"Insp@{m}" for m in packaged) if packaged else "Nenhuma"
        print(
            f"{ac.id:<10} Sem {start_week:<6} Sem {end_week:<6} {fh_entry:<12.1f} {pkg_str}"
        )

    print("\n--- Esforço Aéreo ---")
    fh_2026 = sum(
        result.fh_allocation.get((ac.index, t), 0.0) for ac in fleet for t in T_2026
    )
    fh_2027 = sum(
        result.fh_allocation.get((ac.index, t), 0.0) for ac in fleet for t in T_2027
    )
    print(f"2026: {fh_2026:.1f} FH (meta: {FH_TARGET_2026})")
    print(f"2027: {fh_2027:.1f} FH (meta: {FH_TARGET_2027})")
    print(f"Total: {fh_2026 + fh_2027:.1f} FH")

    print("\n--- Downtime ---")
    print(
        f"SB total:                    {result.sb_downtime_weeks:.1f} semanas-aeronave"
    )
    print(
        f"Inspeções standalone:        {result.standalone_insp_downtime_weeks:.1f} semanas-aeronave"
    )
    print(
        f"Inspeções empacotadas (eco): {result.packaged_insp_savings_weeks:.1f} semanas-aeronave"
    )
    print(
        f"DOWNTIME TOTAL:              {result.total_downtime_weeks:.1f} semanas-aeronave"
    )
    print("=" * 70)
