"""
Otimizador Genético de Parâmetros
===================================
Usa algoritmo genético para evoluir os parâmetros da estratégia,
imitando seleção natural: os melhores parâmetros "sobrevivem" e
geram filhos (com pequenas mutações) para a próxima geração.

Fluxo:
  1. Gera população inicial aleatória de parâmetros
  2. Avalia cada indivíduo via backtest
  3. Seleciona os melhores (elitismo)
  4. Cruza os sobreviventes (crossover)
  5. Aplica mutações aleatórias
  6. Repete por N gerações
  7. Retorna o melhor conjunto de parâmetros encontrado
"""

import random
import copy
import asyncio
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from src.indicators import compute_indicators
from src.strategy import Signal, get_signal


# ── Espaço de busca dos parâmetros ───────────────────────────────────────────

PARAM_SPACE = {
    "ma_fast":         (3,  15,  1),    # (min, max, step)
    "ma_slow":         (15, 50,  1),
    "rsi_period":      (7,  21,  1),
    "rsi_oversold":    (25, 45,  1),
    "rsi_overbought":  (55, 75,  1),
    "bb_period":       (10, 30,  1),
    "bb_std":          (1.5, 3.0, 0.1),
    "stop_loss_pct":   (1.0, 8.0, 0.5),
    "take_profit_pct": (2.0, 15.0, 0.5),
    "trade_size_pct":  (10,  40,  5),
}


@dataclass
class Individual:
    """Um conjunto de parâmetros com sua pontuação (fitness)."""
    ma_fast: int         = 7
    ma_slow: int         = 21
    rsi_period: int      = 14
    rsi_oversold: float  = 35.0
    rsi_overbought: float= 65.0
    bb_period: int       = 20
    bb_std: float        = 2.0
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    trade_size_pct: float  = 20.0

    # Fitness calculado após avaliação
    fitness: float       = -999.0
    win_rate: float      = 0.0
    total_trades: int    = 0
    total_return_pct: float = 0.0
    sharpe: float        = 0.0

    def is_valid(self) -> bool:
        """Garante que os parâmetros são logicamente consistentes."""
        return (
            self.ma_fast < self.ma_slow
            and self.rsi_oversold < self.rsi_overbought
            and self.stop_loss_pct < self.take_profit_pct
            and self.total_trades >= 3  # Mínimo de trades para ser confiável
        )


# ── Geração de indivíduos ─────────────────────────────────────────────────────

def _rand_param(key: str):
    lo, hi, step = PARAM_SPACE[key]
    steps = int(round((hi - lo) / step))
    val = lo + random.randint(0, steps) * step
    return round(val, 2)


def random_individual() -> Individual:
    ind = Individual()
    for key in PARAM_SPACE:
        setattr(ind, key, _rand_param(key))
    # Garante validade básica
    if ind.ma_fast >= ind.ma_slow:
        ind.ma_slow = ind.ma_fast + random.randint(5, 15)
    if ind.rsi_oversold >= ind.rsi_overbought:
        ind.rsi_overbought = ind.rsi_oversold + random.randint(15, 25)
    if ind.stop_loss_pct >= ind.take_profit_pct:
        ind.take_profit_pct = ind.stop_loss_pct * 2
    return ind


# ── Avaliação (fitness) ───────────────────────────────────────────────────────

def evaluate(ind: Individual, df: pd.DataFrame) -> Individual:
    """
    Roda backtest rápido com os parâmetros do indivíduo.
    O fitness combina retorno, win rate e penaliza poucos trades.
    """
    balance = 10_000.0
    asset = 0.0
    buy_price = 0.0
    in_position = False
    pnl_series = []

    for i in range(len(df)):
        window = df.iloc[: i + 1]
        indicators = compute_indicators(window, ind)
        if indicators is None:
            continue

        signal = get_signal(indicators, in_position, buy_price if in_position else None, ind)

        if signal == Signal.BUY and not in_position and balance > 10:
            spend = balance * (ind.trade_size_pct / 100)
            qty = (spend * 0.999) / indicators.close
            balance -= spend
            asset = qty
            buy_price = indicators.close
            in_position = True

        elif signal in (Signal.SELL, Signal.STOP_LOSS, Signal.TAKE_PROFIT) and in_position:
            gross = asset * indicators.close
            net = gross * 0.999
            pnl = net - (asset * buy_price)
            pnl_series.append(pnl)
            balance += net
            asset = 0.0
            in_position = False

    # Fecha posição aberta no último preço
    if in_position and asset > 0:
        last = float(df["close"].iloc[-1])
        net = asset * last * 0.999
        pnl = net - (asset * buy_price)
        pnl_series.append(pnl)
        balance += net

    total_trades = len(pnl_series)
    ind.total_trades = total_trades

    if total_trades < 3:
        ind.fitness = -999.0
        return ind

    wins = sum(1 for p in pnl_series if p > 0)
    total_pnl = sum(pnl_series)
    final_balance = balance
    total_return = ((final_balance - 10_000) / 10_000) * 100

    ind.total_return_pct = round(total_return, 2)
    ind.win_rate = round((wins / total_trades) * 100, 1)

    # Sharpe simplificado (retorno / desvio padrão dos P&Ls)
    if len(pnl_series) > 1:
        arr = np.array(pnl_series)
        std = arr.std()
        ind.sharpe = round(float(arr.mean() / std) if std > 0 else 0, 3)
    else:
        ind.sharpe = 0.0

    # Fitness = retorno * win_rate_bonus * sharpe_bonus - penalidade_poucos_trades
    win_bonus = ind.win_rate / 50       # 1.0 = 50% win rate (neutro)
    sharpe_bonus = max(0, ind.sharpe)
    trade_penalty = max(0, (10 - total_trades) * 2)  # penaliza < 10 trades

    ind.fitness = round(
        total_return * win_bonus * (1 + sharpe_bonus * 0.5) - trade_penalty, 4
    )
    return ind


# ── Operadores genéticos ──────────────────────────────────────────────────────

def crossover(parent_a: Individual, parent_b: Individual) -> Tuple[Individual, Individual]:
    """Troca parâmetros aleatoriamente entre dois pais."""
    child_a = copy.deepcopy(parent_a)
    child_b = copy.deepcopy(parent_b)

    for key in PARAM_SPACE:
        if random.random() < 0.5:
            va = getattr(parent_a, key)
            vb = getattr(parent_b, key)
            setattr(child_a, key, vb)
            setattr(child_b, key, va)

    # Corrige inconsistências
    for child in (child_a, child_b):
        if child.ma_fast >= child.ma_slow:
            child.ma_slow = child.ma_fast + 5
        if child.rsi_oversold >= child.rsi_overbought:
            child.rsi_overbought = child.rsi_oversold + 20
        if child.stop_loss_pct >= child.take_profit_pct:
            child.take_profit_pct = child.stop_loss_pct * 2

    return child_a, child_b


def mutate(ind: Individual, mutation_rate: float = 0.2) -> Individual:
    """Muda aleatoriamente alguns parâmetros com probabilidade mutation_rate."""
    mutated = copy.deepcopy(ind)
    for key in PARAM_SPACE:
        if random.random() < mutation_rate:
            lo, hi, step = PARAM_SPACE[key]
            current = getattr(mutated, key)
            # Perturbação pequena: ±1 a 3 steps
            delta = random.randint(1, 3) * step * random.choice([-1, 1])
            new_val = round(min(hi, max(lo, current + delta)), 2)
            setattr(mutated, key, new_val)

    # Corrige inconsistências após mutação
    if mutated.ma_fast >= mutated.ma_slow:
        mutated.ma_slow = mutated.ma_fast + 5
    if mutated.rsi_oversold >= mutated.rsi_overbought:
        mutated.rsi_overbought = mutated.rsi_oversold + 20
    if mutated.stop_loss_pct >= mutated.take_profit_pct:
        mutated.take_profit_pct = mutated.stop_loss_pct * 2

    mutated.fitness = -999.0  # Precisa ser reavaliado
    return mutated


def tournament_select(population: List[Individual], k: int = 3) -> Individual:
    """Seleciona o melhor de k indivíduos aleatórios (torneio)."""
    contestants = random.sample(population, min(k, len(population)))
    return max(contestants, key=lambda x: x.fitness)


# ── Algoritmo genético principal ──────────────────────────────────────────────

class GeneticOptimizer:
    def __init__(
        self,
        df: pd.DataFrame,
        population_size: int = 40,
        generations: int = 20,
        elite_pct: float = 0.2,
        mutation_rate: float = 0.25,
        logger: Optional[logging.Logger] = None,
    ):
        self.df = df
        self.population_size = population_size
        self.generations = generations
        self.elite_size = max(2, int(population_size * elite_pct))
        self.mutation_rate = mutation_rate
        self.logger = logger or logging.getLogger("optimizer")
        self.history: List[dict] = []

    def _log(self, msg: str):
        self.logger.info(msg)

    def run(self) -> Individual:
        self._log(f"🧬 Iniciando otimização genética")
        self._log(f"   População: {self.population_size} | Gerações: {self.generations}")
        self._log(f"   Candles disponíveis: {len(self.df)}")

        # Geração inicial
        population = [random_individual() for _ in range(self.population_size)]
        population = [evaluate(ind, self.df) for ind in population]
        population.sort(key=lambda x: x.fitness, reverse=True)

        best_ever = population[0]

        for gen in range(1, self.generations + 1):
            # Elitismo: os melhores passam direto
            next_gen: List[Individual] = population[: self.elite_size]

            # Preenche o restante com crossover + mutação
            while len(next_gen) < self.population_size:
                parent_a = tournament_select(population)
                parent_b = tournament_select(population)
                child_a, child_b = crossover(parent_a, parent_b)
                child_a = mutate(child_a, self.mutation_rate)
                child_b = mutate(child_b, self.mutation_rate)
                next_gen.extend([child_a, child_b])

            # Avalia novos indivíduos (elites já foram avaliados)
            for i in range(self.elite_size, len(next_gen)):
                next_gen[i] = evaluate(next_gen[i], self.df)

            population = sorted(next_gen, key=lambda x: x.fitness, reverse=True)[
                : self.population_size
            ]

            best = population[0]
            if best.fitness > best_ever.fitness:
                best_ever = copy.deepcopy(best)

            self._log(
                f"   Gen {gen:>2}/{self.generations} | "
                f"Melhor fitness: {best.fitness:+.2f} | "
                f"Retorno: {best.total_return_pct:+.1f}% | "
                f"Win rate: {best.win_rate:.0f}% | "
                f"Trades: {best.total_trades}"
            )

            self.history.append({
                "generation": gen,
                "best_fitness": best.fitness,
                "best_return": best.total_return_pct,
                "best_win_rate": best.win_rate,
                "avg_fitness": round(
                    sum(x.fitness for x in population if x.fitness > -999) / max(1, len(population)), 4
                ),
            })

        self._log(f"\n🏆 Melhor indivíduo encontrado:")
        self._log(f"   Fitness:   {best_ever.fitness:+.4f}")
        self._log(f"   Retorno:   {best_ever.total_return_pct:+.2f}%")
        self._log(f"   Win rate:  {best_ever.win_rate:.1f}%")
        self._log(f"   Trades:    {best_ever.total_trades}")
        self._log(f"   Sharpe:    {best_ever.sharpe:.3f}")
        self._log(f"   Parâmetros: MA {best_ever.ma_fast}/{best_ever.ma_slow} | "
                  f"RSI {best_ever.rsi_period} ({best_ever.rsi_oversold}/{best_ever.rsi_overbought}) | "
                  f"SL {best_ever.stop_loss_pct}% | TP {best_ever.take_profit_pct}%")

        return best_ever

    def save_history(self, path: str = "logs/optimization_history.json"):
        Path(path).parent.mkdir(exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.history, f, indent=2)
