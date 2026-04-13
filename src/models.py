"""
Fleet Downtime Minimizer - Data Models
MPP30 Manutenção - ITA 2026

Classes para representação de aeronaves, inspeções e regras de manutenção.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import math

from src.config import (
    INSP_INTERVALS,
    INSP100_EXPECTED_WEEKS,
    INSP200_EXPECTED_WEEKS,
    INSP400_EXPECTED_WEEKS,
    SB_DURATION_CEIL,
    HORIZON_WEEKS,
)


@dataclass
class Inspection:
    """Representa uma inspeção futura de uma aeronave."""

    milestone: int  # FH nominal (ex: 300, 400, 600)
    level: int  # Nível da inspeção executada (100, 200 ou 400)
    window_low: int  # Limite inferior da janela efetiva (FH)
    window_high: int  # Limite superior da janela efetiva (FH)
    duration_weeks: float  # Duração esperada (semanas)

    @property
    def tolerance(self) -> int:
        return INSP_INTERVALS[self.level]["tolerance"]


def get_inspection_level(milestone: int) -> int:
    """Retorna o nível da inspeção para um dado milestone.

    400, 800, 1200, ... → Insp400 (inclui 200 e 100)
    200, 600, 1000, ... → Insp200 (inclui 100)
    100, 300, 500, ...  → Insp100
    """
    if milestone % 400 == 0:
        return 400
    elif milestone % 200 == 0:
        return 200
    else:
        return 100


def get_inspection_duration(level: int) -> float:
    """Retorna a duração esperada (semanas) para um nível de inspeção."""
    if level == 400:
        return INSP400_EXPECTED_WEEKS
    elif level == 200:
        return INSP200_EXPECTED_WEEKS
    else:
        return INSP100_EXPECTED_WEEKS


def compute_effective_window(milestone: int) -> Tuple[int, int]:
    """Computa a janela efetiva de execução para um milestone.

    Quando há nesting (ex: @400 FH → Insp400 + Insp200 + Insp100),
    a janela efetiva é a INTERSEÇÃO das janelas individuais.

    A janela de Insp100 (±10 FH) é sempre a mais restritiva.
    """
    return (milestone - 10, milestone + 10)


def compute_future_inspections(fh0: int, max_fh: int = None) -> List[Inspection]:
    """Computa todas as inspeções futuras para uma aeronave.

    Args:
        fh0: FH atual da aeronave (inspeções até aqui já foram realizadas)
        max_fh: FH máximo a considerar (default: fh0 + 800)

    Returns:
        Lista de Inspection ordenada por milestone
    """
    if max_fh is None:
        max_fh = fh0 + 3000

    inspections = []
    milestone = 100
    while milestone <= max_fh:
        if milestone > fh0:  # Apenas inspeções futuras
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
    """Representa uma aeronave da frota."""

    id: str  # Identificador (ex: "ANV-01")
    index: int  # Índice 0-based
    fh0: float  # FH inicial
    available_week: int  # Primeira semana disponível (1-indexed)
    needs_sb: bool  # Precisa de Service Bulletin?
    future_inspections: List[Inspection] = field(default_factory=list)

    def __post_init__(self):
        if not self.future_inspections:
            self.future_inspections = compute_future_inspections(int(self.fh0))

    # @property
    # def fh_to_400(self) -> float:
    #     """FH restantes até o milestone de 400 FH."""
    #     return max(0, 400 - self.fh0)

    # @property
    # def insp400_window(self) -> Tuple[int, int]:
    #     """Janela efetiva da Insp400 (primeira ocorrência futura)."""
    #     for insp in self.future_inspections:
    #         if insp.level == 400:
    #             return (insp.window_low, insp.window_high)
    #     return (390, 410)

    # def inspections_packageable_at_fh(self, fh: float) -> List[Inspection]:
    #     """Retorna inspeções que podem ser empacotadas se a aeronave
    #     entrar em manutenção com o FH dado."""
    #     return [
    #         insp
    #         for insp in self.future_inspections
    #         if insp.window_low <= fh <= insp.window_high
    #     ]

    # def packaging_savings_at_fh(self, fh: float) -> float:
    #     """Retorna o total de semanas de downtime economizadas por
    #     empacotamento se entrar em manutenção com FH dado."""
    #     return sum(
    #         insp.duration_weeks for insp in self.inspections_packageable_at_fh(fh)
    #     )


def build_fleet(aircraft_data: list) -> List[Aircraft]:
    """Constrói a frota a partir dos dados de configuração."""
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
    """Resultado do scheduling de manutenção."""

    # SB schedule: {aircraft_index: start_week}
    sb_schedule: dict = field(default_factory=dict)

    # FH allocation: {(aircraft_index, week): fh}
    fh_allocation: dict = field(default_factory=dict)

    # Standalone inspections: [(aircraft_index, milestone, start_week, duration_weeks)]
    standalone_inspections: list = field(default_factory=list)

    # Packaged inspections: [(aircraft_index, milestone)]
    packaged_inspections: list = field(default_factory=list)

    # Metrics
    total_downtime_weeks: float = 0.0
    sb_downtime_weeks: float = 0.0
    standalone_insp_downtime_weeks: float = 0.0
    packaged_insp_savings_weeks: float = 0.0

    # FH at SB entry: {aircraft_index: fh}
    fh_at_sb_entry: dict = field(default_factory=dict)

    # Solver status
    solver_status: str = ""
    objective_value: float = 0.0
