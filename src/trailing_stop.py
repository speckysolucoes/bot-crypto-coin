"""
Trailing Stop Loss
==================
O stop loss sobe automaticamente junto com o preço,
protegendo o lucro conquistado sem fechar cedo demais.

Exemplo:
  Compra:  $90.000  | Stop inicial: $87.300 (3% abaixo)
  Sobe p/ $95.000   | Stop sobe p/ $92.150 (3% abaixo de $95k)
  Sobe p/ $97.000   | Stop sobe p/ $94.090
  Cai p/  $94.000   | VENDE — lucro garantido de +4.5%

O stop NUNCA desce — só sobe quando o preço sobe.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrailingStop:
    buy_price: float
    trail_pct: float           # % de distância do stop ao preço máximo
    activate_pct: float = 1.0  # só começa a subir após lucro de X%

    _highest_price: float = 0.0
    _stop_price: float = 0.0
    _activated: bool = False

    def __post_init__(self):
        self._highest_price = self.buy_price
        self._stop_price = self.buy_price * (1 - self.trail_pct / 100)

    def update(self, current_price: float) -> bool:
        """
        Atualiza o stop com o preço atual.
        Retorna True se o stop foi acionado (deve vender).
        """
        # Ativa o trailing após lucro mínimo
        if not self._activated:
            profit_pct = ((current_price - self.buy_price) / self.buy_price) * 100
            if profit_pct >= self.activate_pct:
                self._activated = True

        # Atualiza o preço máximo e o stop
        if current_price > self._highest_price:
            self._highest_price = current_price
            new_stop = current_price * (1 - self.trail_pct / 100)
            # Stop nunca desce
            if new_stop > self._stop_price:
                self._stop_price = new_stop

        # Verifica se foi acionado
        return self._activated and current_price <= self._stop_price

    @property
    def stop_price(self) -> float:
        return self._stop_price

    @property
    def highest_price(self) -> float:
        return self._highest_price

    @property
    def activated(self) -> bool:
        return self._activated

    def summary(self) -> str:
        locked = ((self._stop_price - self.buy_price) / self.buy_price) * 100
        return (
            f"TrailingStop | "
            f"Compra: ${self.buy_price:,.2f} | "
            f"Máximo: ${self._highest_price:,.2f} | "
            f"Stop: ${self._stop_price:,.2f} | "
            f"Lucro travado: {locked:+.2f}% | "
            f"Ativo: {'SIM' if self._activated else f'aguardando +{self.activate_pct}%'}"
        )
