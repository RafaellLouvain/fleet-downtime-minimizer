"""
Fleet Downtime Minimizer - Data Models
MPP30 Manutenção - ITA 2026

Classes para representação de aeronaves, inspeções e regras de manutenção.
"""

from dataclasses import dataclass, field
from typing import List, Tuple

from src.config import (
    INSP_INTERVALS,
    INSP100_EXPECTED_WEEKS,
    INSP200_EXPECTED_WEEKS,
    INSP400_EXPECTED_WEEKS,
)


@dataclass
class Inspection:
    """Uma inspeção periódica futura de uma aeronave.

    Cada inspeção tem um milestone nominal de FH (100, 200, 300, ...) e
    deve ser realizada dentro da janela [window_low, window_high]. Quando
    o milestone coincide com um múltiplo maior (ex: 200 ou 400 FH), o nível
    da inspeção é elevado pois a inspeção maior já inclui as menores.
    """

    milestone: int          # FH nominal (ex: 100, 200, 300, 400, 500, ...)
    level: int              # Nível executado (100, 200 ou 400)
    window_low: int         # FH mínimo para realizar (interseção das janelas)
    window_high: int        # FH máximo para realizar
    duration_weeks: float   # Duração esperada (semanas)

    @property
    def tolerance(self) -> int:
        return INSP_INTERVALS[self.level]["tolerance"]


def get_inspection_level(milestone: int) -> int:
    """Retorna o nível da inspeção para um dado milestone de FH.

    Como inspeções de nível maior absorvem as de nível menor (nesting), num
    milestone múltiplo de 400 só executamos a Insp400; num múltiplo de 200
    (mas não 400), a Insp200; nos demais múltiplos de 100, a Insp100.
    """
    if milestone % 400 == 0:
        return 400
    elif milestone % 200 == 0:
        return 200
    else:
        return 100


def get_inspection_duration(level: int) -> float:
    """Duração esperada (semanas) para um nível de inspeção."""
    if level == 400:
        return INSP400_EXPECTED_WEEKS
    elif level == 200:
        return INSP200_EXPECTED_WEEKS
    else:
        return INSP100_EXPECTED_WEEKS


def compute_effective_window(milestone: int) -> Tuple[int, int]:
    """Janela efetiva (FH) em torno do milestone.

    Como a Insp100 tem tolerância ±10 FH (a mais restritiva) e seus
    milestones coincidem com os de Insp200/400, a interseção das janelas
    é sempre [milestone-10, milestone+10].
    """
    return (milestone - 10, milestone + 10)


def compute_future_inspections(fh0: int, max_fh: int = None) -> List[Inspection]:
    """Gera todas as inspeções pendentes a partir de fh0 até max_fh.

    Itera milestones de 100 em 100 FH e cria uma Inspection para cada,
    com nível, janela e duração já computados. Apenas milestones acima
    de fh0 são considerados (inspeções anteriores já foram realizadas).
    """
    if max_fh is None:
        max_fh = fh0 + 3000

    inspections = []
    milestone = 100
    while milestone <= max_fh:
        if milestone > fh0:
            level = get_inspection_level(milestone)
            low, high = compute_effective_window(milestone)
            duration = get_inspection_duration(level)
            inspections.append(
                Inspection(
                    milestone=milestone,
                    level=level,
                    window_low=low,
                    window_high=high,
                    duration_weeks=duration,
                )
            )
        milestone += 100

    return inspections


@dataclass
class Aircraft:
    """Uma aeronave da frota."""

    id: str                 # Identificador (ex: "ANV-01")
    index: int              # Índice 0-based usado nas estruturas do MILP
    fh0: float              # FH acumuladas no início do horizonte
    available_week: int     # Primeira semana em que pode voar (1-indexed)
    needs_sb: bool          # True se precisa do Service Bulletin antes da Insp400
    future_inspections: List[Inspection] = field(default_factory=list)

    def __post_init__(self):
        if not self.future_inspections:
            self.future_inspections = compute_future_inspections(int(self.fh0))


def build_fleet(aircraft_data: list) -> List[Aircraft]:
    """Constrói a frota a partir da lista de dicionários em config.AIRCRAFT_DATA."""
    fleet = []
    for i, data in enumerate(aircraft_data):
        ac = Aircraft(
            id=data["id"],
            index=i,
            fh0=data["fh0"],
            available_week=data["available_week"],
            needs_sb=data["needs_sb"],
        )
        fleet.append(ac)
    return fleet


@dataclass
class ScheduleResult:
    """Saída completa do otimizador (MILP + pós-processamento)."""

    # Decisões do MILP
    sb_schedule: dict = field(default_factory=dict)        # {ac_index: start_week}
    fh_allocation: dict = field(default_factory=dict)      # {(ac_index, week): fh}
    packaged_inspections: list = field(default_factory=list)  # [(ac_index, milestone)]

    # Pós-processamento (inspeções não empacotadas no SB)
    standalone_inspections: list = field(default_factory=list)
    # cada entrada: (ac_index, milestone, start_week, duration_weeks)

    # Métricas agregadas (semanas-aeronave)
    total_downtime_weeks: float = 0.0
    sb_downtime_weeks: float = 0.0
    standalone_insp_downtime_weeks: float = 0.0
    packaged_insp_savings_weeks: float = 0.0

    # FH acumulado na entrada do SB de cada aeronave (validação da R6)
    fh_at_sb_entry: dict = field(default_factory=dict)

    # Diagnóstico do solver
    solver_status: str = ""
    objective_value: float = 0.0
