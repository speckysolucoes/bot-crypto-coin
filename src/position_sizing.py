"""
Position Sizing Dinâmico
=========================
Investe mais quando o sinal é forte, menos quando é fraco.
Baseado no score de confiança (0-100) dos indicadores.

Exemplo com TRADE_SIZE_PCT=20% e saldo de $10.000:

  Confiança 90-100  →  30% do saldo  =  $3.000  (sinal muito forte)
  Confiança 70-89   →  20% do saldo  =  $2.000  (sinal normal)
  Confiança 55-69   →  12% do saldo  =  $1.200  (sinal fraco, entra menor)
  Confiança < 55    →  não entra     =  $0       (filtrado pela estratégia)

Também protege o saldo: nunca arrisca mais que MAX_RISK_PCT em uma única
operação, independente do score de confiança.
"""

from dataclasses import dataclass


@dataclass
class PositionSizer:
    base_pct: float      # % base do saldo (TRADE_SIZE_PCT do .env)
    max_pct:  float = 35.0   # limite máximo absoluto por trade
    min_pct:  float = 5.0    # mínimo para não fazer ordens insignificantes

    def size_pct(self, confidence: int) -> float:
        """
        Retorna o % do saldo a usar com base no score de confiança.
        """
        if confidence >= 85:
            # Sinal muito forte: 1.5x o base
            pct = self.base_pct * 1.5
        elif confidence >= 70:
            # Sinal forte: base normal
            pct = self.base_pct
        elif confidence >= 55:
            # Sinal razoável: 0.6x o base (mais conservador)
            pct = self.base_pct * 0.6
        else:
            # Não deveria chegar aqui (estratégia já filtra < 55)
            pct = self.min_pct

        return round(min(max(pct, self.min_pct), self.max_pct), 1)

    def usdt_amount(self, balance: float, confidence: int) -> float:
        """
        Retorna o valor em USDT a investir.
        """
        pct = self.size_pct(confidence)
        return round(balance * (pct / 100), 2)

    def explain(self, confidence: int) -> str:
        pct = self.size_pct(confidence)
        tier = (
            "muito forte" if confidence >= 85
            else "forte" if confidence >= 70
            else "razoável"
        )
        return f"Confiança {confidence}/100 ({tier}) → {pct}% do saldo"
