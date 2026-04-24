#!/usr/bin/env python3
"""
Fleet Downtime Minimizer
MPP30 Manutenção - ITA 2026
Prof. Danilo Figueiredo

Otimização do scheduling de manutenção de uma frota de 10 aeronaves
para minimizar o downtime total, sujeito a:
  - Inspeções periódicas (100, 200, 400 FH)
  - Service Bulletin mandatório (antes da Insp400)
  - Capacidade do hangar (máx. 2 aeronaves simultâneas)
  - Esforço aéreo programado (1.100 FH em 2026, 1.900 FH em 2027)

Abordagem:
  1. MILP determinístico (PuLP/CBC) para scheduling ótimo
  2. Monte Carlo para validação de robustez com durações estocásticas
     e falhas operacionais (Poisson)

"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import AIRCRAFT_DATA, MC_N_SIMULATIONS
from src.models import build_fleet, ScheduleResult
from src.optimizer import solve_milp, print_schedule
from src.simulator import run_monte_carlo
from src.visualizer import generate_all_plots


def main():
    print("=" * 70)
    print("  FLEET DOWNTIME MINIMIZER")
    print("  MPP30 Manutenção - ITA 2026")
    print("=" * 70)

    # ----------------------------------------------------------------
    # 1. Construir frota
    # ----------------------------------------------------------------
    print("\n[1/4] Construindo frota...")
    fleet = build_fleet(AIRCRAFT_DATA)

    print(f"  {len(fleet)} aeronaves carregadas:")
    for ac in fleet:
        sb_str = "SB necessário" if ac.needs_sb else "Sem SB"
        avail = (
            f"disponível semana {ac.available_week}"
            if ac.available_week > 1
            else "disponível"
        )
        n_insp = len(ac.future_inspections)
        print(
            f"    {ac.id}: {ac.fh0} FH, {avail}, {sb_str}, {n_insp} inspeções futuras"
        )

    # ----------------------------------------------------------------
    # 2. Resolver MILP
    # ----------------------------------------------------------------
    print("\n[2/4] Resolvendo MILP (otimização determinística)...")
    result = solve_milp(fleet, verbose=True)

    if result.solver_status != "Optimal":
        print(f"\nERRO: Solver retornou status '{result.solver_status}'.")
        print("Verifique as restrições e parâmetros.")
        sys.exit(1)

    print_schedule(fleet, result)

    # ----------------------------------------------------------------
    # 3. Monte Carlo
    # ----------------------------------------------------------------
    print("\n[3/4] Executando simulação Monte Carlo...")

    # 3a. Sem falhas operacionais
    print("\n  --- Monte Carlo SEM falhas operacionais ---")
    mc_no_fail = run_monte_carlo(
        fleet,
        result,
        n_simulations=MC_N_SIMULATIONS,
        with_failures=False,
        verbose=True,
    )

    # 3b. Com falhas operacionais
    print("\n  --- Monte Carlo COM falhas operacionais ---")
    mc_with_fail = run_monte_carlo(
        fleet,
        result,
        n_simulations=MC_N_SIMULATIONS,
        with_failures=True,
        verbose=True,
    )

    # ----------------------------------------------------------------
    # 4. Visualizações
    # ----------------------------------------------------------------
    print("\n[4/4] Gerando visualizações...")
    generate_all_plots(fleet, result, mc_results=mc_with_fail)

    # ----------------------------------------------------------------
    # Resumo final
    # ----------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  RESUMO FINAL")
    print("=" * 70)
    print(f"\n  Schedule determinístico:")
    print(f"    Downtime total:  {result.total_downtime_weeks:.1f} semanas-aeronave")
    print(f"    SB downtime:     {result.sb_downtime_weeks:.1f} semanas-aeronave")
    print(
        f"    Standalone insp: {result.standalone_insp_downtime_weeks:.1f} semanas-aeronave"
    )
    print(
        f"    Packaging eco:   {result.packaged_insp_savings_weeks:.1f} semanas-aeronave"
    )

    print(f"\n  Monte Carlo (sem falhas, {MC_N_SIMULATIONS} sim.):")
    print(
        f"    Downtime médio:  {mc_no_fail.mean_downtime:.1f} ± {mc_no_fail.std_downtime:.1f}"
    )
    print(
        f"    IC 90%:          [{mc_no_fail.p5_downtime:.1f}, {mc_no_fail.p95_downtime:.1f}]"
    )
    print(f"    P(violação):     {mc_no_fail.prob_constraint_violation:.1%}")

    print(f"\n  Monte Carlo (com falhas, {MC_N_SIMULATIONS} sim.):")
    print(
        f"    Downtime médio:  {mc_with_fail.mean_downtime:.1f} ± {mc_with_fail.std_downtime:.1f}"
    )
    print(
        f"    IC 90%:          [{mc_with_fail.p5_downtime:.1f}, {mc_with_fail.p95_downtime:.1f}]"
    )
    print(f"    P(violação):     {mc_with_fail.prob_constraint_violation:.1%}")
    print(f"    Falhas (médio):  {mc_with_fail.mean_failure_downtime:.1f} semanas")

    print(f"\n  Gráficos salvos em: results/")
    print("=" * 70)


if __name__ == "__main__":
    main()
