# Fleet Downtime Minimizer - Planejamento

**MPP30 Manutencao - ITA 2026**
**Prof. Danilo Figueiredo**
**Autor: Rafael Lucas de Albuquerque Louvain**

---

## STEP 1: Dissecacao do Problema

### 1.1 Contextualizacao do Problema

Uma frota de 10 aeronaves em fase inicial de operacao precisa cumprir um esforco aereo programado (1.100 FH no restante de 2026 + 1.900 FH em 2027 = 3.000 FH total) enquanto realiza:

1. **Inspecoes periodicas** (100FH, 200FH, 400FH) com duracoes estocasticas (distribuicao triangular)
2. **Um Service Bulletin (SB) mandatorio** que deve ser aplicado em cada aeronave antes da sua inspecao de 400FH, com duracao de ~14-17 semanas

O **objetivo** e planejar semanalmente a distribuicao de horas de voo e os momentos de parada para SB/inspecoes, **minimizando o downtime total da frota** (fleet maintenance downtime) enquanto cumpre todo o esforco aereo demandado.

A capacidade do hangar limita a **2 aeronaves simultaneas** em manutencao.

---

### 1.2 Condicoes Iniciais

| Anv | Idade (FH) | Status | FH ate 400 (SB deadline) | Proximas inspecoes iminentes |
|-----|-----------|--------|--------------------------|------------------------------|
| 01  | 220       | Operacional | 180 | Insp100 @300 |
| 02  | 275       | Operacional | 125 | Insp100 @300 |
| 03  | 215       | Operacional | 185 | Insp100 @300 |
| 04  | 240       | Operacional | 160 | Insp100 @300 |
| 05  | 51        | Operacional | 349 | Insp100 @100 |
| 06  | 300       | Operacional | **100** (URGENTE) | **Insp400 @400** |
| 07  | 180       | Operacional | 220 | Insp200 @200 |
| 08  | 110       | Operacional | 290 | Insp200 @200 |
| 09  | 0         | Entrega AGO/26 | 400 | Insp100 @100 |
| 10  | 0         | Entrega DEZ/26 | 400 | Insp100 @100 |

**Nota:** Anv 06 e o caso mais critico - apenas 100 FH de margem antes da Insp400, e o SB deve ser aplicado ANTES dela.

---

### 1.3 Constraints, Regras e Limitacoes

#### A) Inspecoes Periodicas

1. **Tipos e periodicidade:**
   - **Insp 100FH**: a cada 100 FH. Duracao ~ Triang(24, 48, 72) horas
   - **Insp 200FH**: a cada 200 FH. Duracao ~ Triang(72, 96, 168) horas. **Inclui tarefas da Insp100**
   - **Insp 400FH**: a cada 400 FH. Duracao ~ Triang(168, 192, 336) horas. **Inclui tarefas da Insp100 e Insp200**

2. **Empacotamento (nesting):**
   - Quando multiplas inspecoes coincidem, executa-se a de maior nivel (que inclui as menores)
   - Calendario de inspecoes para uma aeronave:
     - 100 FH -> Insp100
     - 200 FH -> Insp200 (inclui 100)
     - 300 FH -> Insp100
     - 400 FH -> Insp400 (inclui 100 + 200)
     - 500 FH -> Insp100
     - 600 FH -> Insp200 (inclui 100)
     - ...e assim por diante

3. **Tolerancia (+/-10% do intervalo de CADA inspecao):**
   - Insp100: +/-10 FH
   - Insp200: +/-20 FH
   - Insp400: +/-40 FH

4. **Regra dos ciclos menores:** Quando inspecoes se acumulam (ex: na marca 200FH, temos Insp200 + Insp100), a janela efetiva e a **intersecao** das janelas individuais, pois a inspecao de ciclo menor deve respeitar seu proprio intervalo.
   - Exemplo @200 FH: Insp200 window [180,220] intersecao Insp100 window [190,210] -> **[190, 210]**
   - Exemplo @400 FH: Insp400 [360,440] intersecao Insp200 [380,420] intersecao Insp100 [390,410] -> **[390, 410]**

5. **Antecipacoes:** O intervalo reinicia do ponto de execucao. Se fizer Insp100 em 92 FH, a proxima vence em 192 FH (92+100), nao em 200 FH. Antecipar e quase sempre subotimo pois desperdiça vida util E desalinha o nesting.

6. **Postergacoes:** Nao alteram o vencimento das inspecoes subsequentes. Se fizer Insp100 em 108 FH, a proxima continua vencendo em 200 FH.

7. **Apenas horas de voo (FH):** Nao ha intervalos calendaricos para vencimento de inspecoes.

#### B) Service Bulletin (SB) Mandatorio

1. **Deadline:** Deve ser aplicado ANTES da inspecao de 400FH de cada aeronave
2. **Duracao:** ~ Triang(14, 15, 17) semanas ~ 15 semanas em media
3. **Aplica-se a:** Aeronaves 01-08 (ja entregues). Anv 09 e 10 recebem correcao na producao.

#### C) Capacidade e Recursos

1. **Hangar:** Maximo 2 aeronaves simultaneamente em manutencao
2. **Esforco aereo:** 1.100 FH restante de 2026 + 1.900 FH em 2027 = 3.000 FH total
3. **Horizonte de planejamento:** ~37 semanas (resto de 2026) + 52 semanas (2027) = ~89 semanas

#### D) Objetivo

**Minimizar o fleet maintenance downtime total**, ou seja, a soma de todos os periodos em que aeronaves estao indisponiveis para operacao (em manutencao), enquanto:
- Cumpre-se 100% do esforco aereo programado
- Todas as inspecoes sao realizadas dentro das janelas permitidas
- O SB e aplicado em cada aeronave antes de sua Insp400
- Nao se excedem 2 aeronaves simultaneas no hangar

---

### 1.4 Analise de Criticidade por Aeronave

**Urgencia do SB (ordenada por FH restantes ate 400):**

| Prioridade | Anv | FH restantes ate 400 | Semanas de voo ate 400* | Observacao |
|-----------|-----|---------------------|------------------------|------------|
| 1 | 06 | 100 FH | ~3-4 sem | SB URGENTE - deve entrar logo |
| 2 | 02 | 125 FH | ~4-5 sem | Critico |
| 3 | 04 | 160 FH | ~5-6 sem | Alto |
| 4 | 01 | 180 FH | ~6-7 sem | Alto |
| 5 | 03 | 185 FH | ~6-7 sem | Alto |
| 6 | 07 | 220 FH | ~7-8 sem | Medio |
| 7 | 08 | 290 FH | ~10-11 sem | Baixo |
| 8 | 05 | 349 FH | ~12-13 sem | Baixo |
| 9 | 09 | 400 FH | N/A (chega AGO/26) | Sem SB |
| 10 | 10 | 400 FH | N/A (chega DEZ/26) | Sem SB |

**Insight critico:** A Anv 06 tem apenas 100 FH de margem. Como o SB leva ~15 semanas, ela precisa entrar em manutencao IMEDIATAMENTE ou voar muito pouco enquanto aguarda slot.

---

### 1.5 Decisoes Tomadas (Alinhamento)

| # | Decisao | Resposta |
|---|---------|----------|
| 1 | SB aplica-se a quais aeronaves? | **Apenas Anv 01-08** (09/10 recebem correcao na producao) |
| 2 | SB pode ser empacotado com inspecoes? | **Sim** - inspecoes que vencem durante SB sao feitas na mesma parada |
| 3 | Data de inicio do planejamento | **13 de Abril de 2026** (~37 semanas em 2026, 52 em 2027 = ~89 semanas) |
| 4 | Valor de referencia para duracoes | **Media E[X] = (a+b+c)/3** + Monte Carlo para robustez |

### 1.6 Insight Estrategico: Controle da Taxa de Acumulo de FH

O problema NAO e apenas de scheduling de manutencao -- e um problema de **co-otimizacao**:
1. **Alocacao semanal de FH** a cada aeronave (controla quando cada uma atinge milestones)
2. **Scheduling de manutencao** (quando cada aeronave entra/sai do hangar)

Podemos **desacelerar** aeronaves que estao proximas de deadlines (ex: Anv 06) atribuindo-lhes menos FH/semana, enquanto **aceleramos** as que tem mais margem. Isso e uma variavel de decisao poderosa.

**Nota:** "Downtime" = tempo em que a aeronave esta no hangar (manutencao), nao tempo sem voar.

---

### 1.7 Duracoes Esperadas

| Evento | Triang(min, moda, max) | Esperanca E[X] | Em semanas |
|--------|----------------------|----------------|------------|
| Insp100 | (24, 48, 72) horas | 48h = 2 dias | ~0.3 sem |
| Insp200 | (72, 96, 168) horas | 112h ~ 4.7 dias | ~0.7 sem |
| Insp400 | (168, 192, 336) horas | 232h ~ 9.7 dias | ~1.4 sem |
| SB | (14, 15, 17) semanas | 15.3 semanas | ~15.3 sem |

**Nota:** E[Triang(a,b,c)] = (a+b+c)/3. O SB e ordens de magnitude mais longo que qualquer inspecao, fazendo a otimizacao do scheduling do SB o fator dominante.

---

### 1.8 Pegadinhas e Sutilezas Identificadas

**C1. A Anv 06 e uma armadilha temporal**
- Com 300 FH, esta a apenas 100 FH da Insp400
- O SB leva ~15 semanas e deve ser completado ANTES da Insp400
- **Estrategia**: controlar FH da Anv 06 para nao ultrapassar 410 FH antes do SB

**C2. Antecipacao penaliza, postergacao tambem penaliza**
- Antecipar = perde vida util restante e desalinha nesting
- Postergar = encurta o intervalo real ate a proxima inspecao
- O OTIMO e realizar a inspecao exatamente no milestone

**C3. O SB domina o downtime por ordens de magnitude**
- SB: ~15 semanas vs. Insp400: ~1.4 semanas
- Otimizar o scheduling do SB e MUITO mais impactante que otimizar inspecoes

**C4. O empacotamento SB + inspecoes e uma otimizacao poderosa**
- Se durante as ~15 semanas de SB uma inspecao vence, pode ser feita sem downtime adicional
- E ESTRATEGICO planejar o SB para coincidir com o milestone da Insp400

**C5. Aeronaves no hangar NAO acumulam FH**
- Enquanto no SB (~15 semanas), a aeronave esta congelada em FH

**C6. Formacao de filas e inevitavel**
- 8 aeronaves precisam de SB, mas so cabem 2 no hangar
- 4 lotes x 15 semanas = 60 semanas minimo
- **Tensao central**: voar gera FH que aproxima do deadline, mas parar de voar prejudica o esforco aereo

**C7. Anv 09 e 10 aliviam a pressao sobre o esforco aereo**
- Nao precisam de SB, sao "reforcos" puros quando chegam

**C8. O esforco aereo de 2027 e 73% maior que 2026**
- 2026: ~30 FH/semana vs. 2027: ~36.5 FH/semana
- Idealmente, a maioria dos SBs deve ser concluida em 2026 quando a demanda e menor

**C9. Duracoes estocasticas criam risco de cascata**
- SB mais longo que o esperado atrasa a proxima aeronave, que continua voando e acumula FH

---

### 1.9 Tradeoffs Identificados

**F1. Voar vs. Esperar:** Voar mais -> aproxima deadlines; voar menos -> prejudica esforco aereo.

**F2. Antecipar vs. Milestone:** Antecipar permite empacotar mas desperdiça vida util.

**F3. Priorizar urgentes vs. Balancear:** Priorizar Anv 06/02 protege deadlines, mas pode criar urgencia nas restantes.

**F4. Conservador vs. Agressivo:** Mais buffer = mais downtime mas menor risco; sem buffer = menos downtime mas vulneravel.

**F5. Downtime total vs. Distribuicao:** Restricao de 2 slots naturalmente distribui as manutencoes.

---

---

## STEP 2: Modelagem Matematica e Computacional

### 2.1 Natureza do Problema

#### Classificacao
Este e um **problema de scheduling em maquinas paralelas com alocacao de recursos acoplada**:
- **Scheduling**: 8 "jobs" (SBs) em 2 "maquinas" (slots de hangar), com restricoes de precedencia e deadlines variaveis
- **Alocacao de recursos**: distribuicao continua de FH semanais entre aeronaves
- **Acoplamento**: os deadlines dos jobs dependem da alocacao de recursos (quanto mais uma aeronave voa, mais rapido atinge o deadline do SB)

Na literatura, o componente de scheduling e do tipo **P2|prec,d_j|SumC_j** (2 maquinas paralelas, precedencias, deadlines, minimizar soma dos tempos de conclusao) -- NP-hard em geral, mas tratavel para 8 jobs.

#### Variaveis de Decisao
Duas familias acopladas:

1. **x_{i,t}** >= 0 (continua): horas de voo da aeronave i na semana t
2. **s_i** in Z+ (inteira): semana de inicio do SB para aeronave i in {1..8}

#### Grandezas Derivadas
- **FH_i(t)** = FH0_i + Sum_{tau=1}^{t} x_{i,tau}: FH acumuladas da aeronave i no fim da semana t
- **y_{i,t}** in {0,1}: aeronave i esta em manutencao na semana t (derivada de s_i e do schedule de inspecoes)

---

### 2.2 Insight Fundamental: O que e realmente otimizavel?

**O downtime por SB e FIXO:** 8 aeronaves x 15.33 semanas = **122.67 aeronaves-semana** -- independente do schedule.

**O que e variavel:** downtime por inspecoes standalone (nao empacotadas com SB).

**Portanto:** minimizar downtime total equivale a **maximizar inspecoes empacotadas dentro dos periodos de SB**.

#### Como funciona o empacotamento?
Durante o SB (~15 semanas), a aeronave esta no hangar e seu FH esta congelado. Se, no momento de entrada, o FH da aeronave esta dentro da janela de uma inspecao devida, essa inspecao pode ser realizada DENTRO do periodo de SB sem adicionar downtime.

**Condicao de empacotamento:** inspecao com milestone M e tolerancia +/-tol e empacotavel se:
```
FH_i(s_i) in [M - tol, M + tol]
```

#### Estrategia otima: entrar no SB na janela da Insp400
A Insp400 e a inspecao mais longa (~1.4 semanas standalone). Se cada aeronave entrar no SB quando FH in [390, 410]:
- O SB e feito
- A Insp400 e empacotada (economia de ~1.4 semanas/aeronave)
- Para 8 aeronaves: economia potencial de ~11.2 aeronaves-semana

Adicionalmente, na marca ~400 FH, a Insp100 e Insp200 tambem estao incluidas no nesting da Insp400, entao todas sao empacotadas.

---

### 2.3 Formulacao MILP

#### Conjuntos
- I = {1,...,10}: aeronaves
- I_SB = {1,...,8}: aeronaves que precisam de SB
- T = {1,...,89}: semanas (horizonte de planejamento)
- T_2026 = {1,...,37}: semanas em 2026
- T_2027 = {38,...,89}: semanas em 2027
- J_i: conjunto de inspecoes da aeronave i no horizonte

#### Parametros
| Parametro | Descricao |
|-----------|-----------|
| FH0_i | FH inicial da aeronave i |
| D_SB = 16 | Duracao do SB em semanas (ceil de E[Triang(14,15,17)]=15.33) |
| d_j | Duracao da inspecao j em semanas |
| M_j | Milestone de FH da inspecao j |
| tol_j | Tolerancia da inspecao j (10% do intervalo) |
| avail_i | Primeira semana disponivel da aeronave i |
| FH_max | FH maximo razoavel por semana por aeronave (~10-15 FH) |

#### Variaveis de Decisao
| Variavel | Tipo | Descricao |
|----------|------|-----------|
| x_{i,t} | Continua >= 0 | FH da aeronave i na semana t |
| s_i | Inteira >= 1 | Semana de inicio do SB da aeronave i in I_SB |
| p_{i,j} | Binaria {0,1} | 1 se inspecao j da aeronave i e empacotada no SB |
| w_{i,j} | Inteira >= 1 | Semana de inicio da inspecao j da aeronave i (se standalone) |

#### Funcao Objetivo
```
min Sum_{i in I_SB} D_SB + Sum_{i in I} Sum_{j in J_i} d_j x (1 - p_{i,j})
```
Equivalentemente (o primeiro termo e constante):
```
max Sum_{i in I} Sum_{j in J_i} d_j x p_{i,j}
```
**Maximizar o downtime total empacotado.**

#### Restricoes

**R1. Esforco aereo:**
```
Sum_{i in I} Sum_{t in T_2026} x_{i,t} = 1100
Sum_{i in I} Sum_{t in T_2027} x_{i,t} = 1900
```

**R2. Nao voar durante manutencao:**
```
x_{i,t} = 0  se aeronave i esta em manutencao na semana t
```
(Aeronave esta em manutencao se: t in [s_i, s_i + D_SB - 1] para SB, ou t in [w_{i,j}, w_{i,j} + ceil(d_j) - 1] para inspecao standalone j)

**R3. Capacidade do hangar (max 2 simultaneas):**
```
Sum_{i in I} y_{i,t} <= 2   para todo t in T
```
onde y_{i,t} = 1 se aeronave i esta em qualquer tipo de manutencao na semana t.

**R4. SB antes da Insp400:**
```
s_i + D_SB - 1 <= semana em que aeronave i atinge 390 FH
```

**R5. Janelas de inspecao:**
Para cada inspecao j com milestone M_j e tolerancia tol_j:
```
FH_i(t_start_j) in [M_j - tol_j, M_j + tol_j]
```

**R6. Empacotamento valido:**
p_{i,j} = 1 apenas se FH_i(s_i) in [M_j - tol_j, M_j + tol_j]

**R7. Disponibilidade:**
```
x_{i,t} = 0   para todo t < avail_i
```

**R8. Limites de voo:**
```
x_{i,t} <= FH_max   para todo i, t
```

---

### 2.4 Complexidade e Tratabilidade

#### Dimensao do problema
- ~890 variaveis continuas (x_{i,t}: 10 x 89)
- ~8 variaveis inteiras (s_i)
- ~30-40 variaveis binarias (p_{i,j} para empacotamento)
- ~30-40 variaveis inteiras (w_{i,j} para inspecoes standalone)
- ~300+ restricoes

**Veredito:** Problema de tamanho MODERADO. Soluvel por MILP com solver gratuito (CBC/HiGHS via PuLP) em segundos a minutos.

#### Linearidade
- Objetivo: linear em p_{i,j}
- R1: linear em x_{i,t}
- R2: linearizavel com big-M
- R3: linear em y_{i,t}
- R5-R6: FH_i(t) e linear em x_{i,t}, janelas sao lineares -> big-M para condicional

**O problema E linearizavel -> MILP e viavel.**

---

### 2.5 Abordagens Consideradas

| # | Abordagem | Otimalidade | Complexidade | Estocastico | Adequacao |
|---|-----------|-------------|-------------|-------------|-----------|
| 1 | MILP (PuLP/HiGHS) | Otimo global | Media | Nao (deterministico) | 4/5 |
| 2 | CP-SAT (OR-Tools) | Otimo/near-otimo | Media | Nao | 4/5 |
| 3 | Heuristica gulosa + LP | Near-otimo | Baixa | Nao | 3/5 |
| 4 | Simulacao + Metaheuristica | Near-otimo | Alta | Sim | 3/5 |
| 5 | **MILP + Monte Carlo** | **Otimo + Robusto** | **Media-Alta** | **Sim** | **5/5** |

#### Abordagem Escolhida: #5 (MILP + Monte Carlo)

**Fase A -- Otimizacao Deterministica (MILP):**
Resolve o scheduling otimo usando duracoes esperadas. Encontra: ordem e timing dos SBs, alocacao semanal de FH, quais inspecoes sao empacotadas vs. standalone.

**Fase B -- Simulacao Monte Carlo:**
Valida o schedule da Fase A com duracoes estocasticas (amostrando das distribuicoes triangulares). Mede: distribuicao do downtime total, probabilidade de violacao de constraints, cenarios de pior caso.

**Fase C -- Analise de Robustez e Buffers:**
Se a Fase B revelar vulnerabilidades: adiciona buffers ao schedule, re-otimiza com constraints mais apertadas, quantifica o tradeoff buffer vs. downtime.

**Fase D -- Contingencia (qualitativa + quantitativa):**
Cenarios: falha inesperada, SB prolongado (17 sem), findings extras.

---

### 2.6 Estrategias de Confiabilidade e Incerteza

#### 2.6.1 Fontes de incerteza
1. **Duracao do SB**: Triang(14, 15, 17) semanas -- sigma ~ 0.75 semanas
2. **Duracao das inspecoes**: Triang com variancias menores
3. **Falhas inesperadas**: eventos discretos nao modelados nas distribuicoes
4. **Disponibilidade de recursos**: pecas, ferramentas, mao de obra

#### 2.6.2 Estrategias de mitigacao

**Buffer temporal entre SBs consecutivos:**
- Entre a saida de uma aeronave e a entrada da proxima no mesmo slot, deixar 1-2 semanas de buffer
- Absorve atrasos no SB anterior sem cascatear para o proximo

**Margem no FH de entrada:**
- Ao inves de entrar no SB em FH = 410 (limite superior), entrar em FH ~ 390-400

**Reserva de capacidade do hangar:**
- Evitar ocupar 2 slots 100% do tempo -- deixar semanas com 1 slot livre para emergencias

#### 2.6.3 Modelagem de falhas

O enunciado diz que "consideracoes sobre eventuais falhas nas aeronaves, disponibilidade de recursos e formacao de filas serao pontuadas." Portanto:

1. **Falhas aleatorias**: processo de Poisson com lambda = 0.02 falhas/semana/aeronave (~1 falha/ano/aeronave)
2. **Reparo corretivo**: duracao ~ Triang(0.5, 1, 2) semanas
3. **Impacto no hangar**: falha compete por slot de hangar com SB/inspecoes planejadas
4. **Formacao de filas**: se 2 slots ocupados e aeronave falha, ela fica em fila (AOG)

---

### 2.7 Arquitetura da Solucao (Implementacao)

```
fleet-downtime-minimizer/
├── src/
│   ├── config.py       # Parametros do problema
│   ├── models.py       # Classes Aircraft, Inspection, ScheduleResult
│   ├── optimizer.py     # Formulacao e solucao MILP (PuLP/CBC)
│   ├── simulator.py     # Simulacao Monte Carlo
│   └── visualizer.py    # Gantt chart, perfis FH, histograma MC
├── docs/
│   └── PLANNING.md      # Este documento
├── main.py              # Entry point (4 fases)
├── requirements.txt     # Dependencias
└── results/             # Outputs (graficos)
```

#### Dependencias Python
```
pulp>=2.7          # MILP solver (inclui CBC)
numpy>=1.24        # Computacao numerica
scipy>=1.10        # Distribuicoes estatisticas (triangular)
matplotlib>=3.7    # Visualizacao (Gantt, graficos)
pandas>=2.0        # Manipulacao de dados tabulares
```

---

### 2.8 Algoritmo Simplificado (Pseudocodigo)

```
# Fase A: Otimizacao Deterministica
1. Definir parametros: frota, inspecoes, duracoes esperadas
2. Para cada aeronave i in {1..8}:
   a. Calcular milestones futuros de inspecao
   b. Identificar o FH ideal de entrada no SB (proximo a um milestone)
   c. Calcular semanas de voo necessarias para atingir esse FH
3. Formular MILP:
   a. Variaveis: s_i (start SB), x_{i,t} (FH/semana)
   b. Objetivo: max empacotamento
   c. Restricoes: hangar <= 2, esforco aereo, janelas de inspecao
4. Resolver com PuLP/CBC
5. Extrair schedule otimo

# Fase B: Monte Carlo
6. Para k = 1 a N_sim:
   a. Amostrar duracoes de Triang() para cada SB e inspecao
   b. Simular o schedule da Fase A com duracoes amostradas
   c. Registrar: downtime total, violacoes de constraints
7. Calcular estatisticas: media, P5, P95, probabilidade de sucesso

# Fase C: Ajuste de Buffers
8. Se P(violacao) > limiar:
   a. Identificar gargalos
   b. Adicionar buffers
   c. Re-resolver MILP com constraints ajustadas
   d. Repetir Monte Carlo

# Fase D: Resultados
9. Gerar Gantt chart, perfis de FH, metricas
10. Documentar contingencias e recomendacoes
```

---

### 2.9 Verificacao de Viabilidade (Sanity Check)

**O esforco aereo e viavel com as restricoes de manutencao?**

Capacidade bruta de voo:
- Anv 01-08: 8 x 89 semanas = 712 aeronave-semanas
- Anv 09: 73 semanas
- Anv 10: 55 semanas
- **Total: 840 aeronave-semanas**

Downtime minimo (SB + inspecoes empacotadas):
- SB: 8 x 16 = 128 aeronave-semanas
- Inspecoes standalone (estimativa): ~30 inspecoes x 0.5 semanas = 15 aeronave-semanas (pessimista)
- **Total downtime: ~143 aeronave-semanas**

Aeronave-semanas disponiveis para voo: 840 - 143 = **697 aeronave-semanas**

FH necessarios: 3.000 FH
FH por aeronave-semana necessario: 3000 / 697 = **4.3 FH/semana/aeronave**

Isso e ~37 minutos de voo por dia por aeronave disponivel. **Totalmente viavel.**

**O hangar suporta 8 SBs em 89 semanas com 2 slots?**

Com 2 slots e SBs de 16 semanas:
- Capacidade: 2 slots x 89 semanas / 16 semanas = ~11 SBs possiveis
- Necessidade: 8 SBs
- **Margem: 3 SBs extras -> ~48 semanas de folga no hangar**
