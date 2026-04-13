"""
Fleet Downtime Minimizer - Problem Configuration
MPP30 Manutenção - ITA 2026

All problem parameters and initial conditions.
"""

# =============================================================================
# Horizonte de Planejamento
# =============================================================================
PLANNING_START = "2026-04-13"
WEEKS_2026 = 37          # 13/Abr a 31/Dez 2026
WEEKS_2027 = 52          # 01/Jan a 31/Dez 2027
HORIZON_WEEKS = WEEKS_2026 + WEEKS_2027  # 89 semanas

# Semanas por período (1-indexed)
T_2026 = list(range(1, WEEKS_2026 + 1))        # semanas 1..37
T_2027 = list(range(WEEKS_2026 + 1, HORIZON_WEEKS + 1))  # semanas 38..89
T_ALL = list(range(1, HORIZON_WEEKS + 1))       # semanas 1..89

# =============================================================================
# Esforço Aéreo
# =============================================================================
FH_TARGET_2026 = 1100    # FH total da frota no restante de 2026
FH_TARGET_2027 = 1900    # FH total da frota em 2027
FH_TARGET_TOTAL = FH_TARGET_2026 + FH_TARGET_2027  # 3000 FH

# =============================================================================
# Capacidade
# =============================================================================
HANGAR_CAPACITY = 2       # Máximo de aeronaves em manutenção simultânea
FH_MAX_WEEK = 15.0        # FH máximo por aeronave por semana

# =============================================================================
# Durações - Distribuições Triangulares (min, moda, max)
# =============================================================================
# Inspeções (em horas)
INSP100_DURATION_HOURS = (24, 48, 72)
INSP200_DURATION_HOURS = (72, 96, 168)
INSP400_DURATION_HOURS = (168, 192, 336)

# Service Bulletin (em semanas)
SB_DURATION_WEEKS_TRIANG = (14, 15, 17)

# Valores esperados E[X] = (a + b + c) / 3
HOURS_PER_WEEK = 7 * 24  # 168 horas/semana

INSP100_EXPECTED_HOURS = sum(INSP100_DURATION_HOURS) / 3   # 48h
INSP200_EXPECTED_HOURS = sum(INSP200_DURATION_HOURS) / 3   # 112h
INSP400_EXPECTED_HOURS = sum(INSP400_DURATION_HOURS) / 3   # 232h

INSP100_EXPECTED_WEEKS = INSP100_EXPECTED_HOURS / HOURS_PER_WEEK  # ~0.286
INSP200_EXPECTED_WEEKS = INSP200_EXPECTED_HOURS / HOURS_PER_WEEK  # ~0.667
INSP400_EXPECTED_WEEKS = INSP400_EXPECTED_HOURS / HOURS_PER_WEEK  # ~1.381

SB_EXPECTED_WEEKS = sum(SB_DURATION_WEEKS_TRIANG) / 3  # ~15.33
SB_DURATION_CEIL = 16     # Arredondamento para MILP (semanas inteiras)

# =============================================================================
# Inspeções - Intervalos e Tolerâncias
# =============================================================================
INSP_INTERVALS = {
    100: {"interval": 100, "tolerance": 10},   # ±10 FH
    200: {"interval": 200, "tolerance": 20},   # ±20 FH
    400: {"interval": 400, "tolerance": 40},   # ±40 FH
}

# =============================================================================
# Falhas Operacionais (Processo de Poisson)
# =============================================================================
FAILURE_RATE = 0.02           # λ = 0.02 falhas/semana/aeronave (~1/ano)
REPAIR_DURATION_WEEKS = (0.5, 1, 2)  # Triang(min, moda, max) em semanas

# =============================================================================
# Frota - Condições Iniciais
# =============================================================================
AIRCRAFT_DATA = [
    {"id": "ANV-01", "fh0": 220, "available_week": 1, "needs_sb": True},
    {"id": "ANV-02", "fh0": 275, "available_week": 1, "needs_sb": True},
    {"id": "ANV-03", "fh0": 215, "available_week": 1, "needs_sb": True},
    {"id": "ANV-04", "fh0": 240, "available_week": 1, "needs_sb": True},
    {"id": "ANV-05", "fh0":  51, "available_week": 1, "needs_sb": True},
    {"id": "ANV-06", "fh0": 300, "available_week": 1, "needs_sb": True},
    {"id": "ANV-07", "fh0": 180, "available_week": 1, "needs_sb": True},
    {"id": "ANV-08", "fh0": 110, "available_week": 1, "needs_sb": True},
    {"id": "ANV-09", "fh0":   0, "available_week": 16, "needs_sb": False},
    {"id": "ANV-10", "fh0":   0, "available_week": 34, "needs_sb": False},
]

N_AIRCRAFT = len(AIRCRAFT_DATA)
N_SB_AIRCRAFT = sum(1 for a in AIRCRAFT_DATA if a["needs_sb"])  # 8

# =============================================================================
# Monte Carlo
# =============================================================================
MC_N_SIMULATIONS = 1000
MC_RANDOM_SEED = 42
