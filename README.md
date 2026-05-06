# CryptoBot 🤖

Bot de trading de criptomoedas com estratégia de **Médias Móveis + RSI + Bandas de Bollinger**.

Suporta **Binance**, **Bybit** e **KuCoin** via [ccxt](https://github.com/ccxt/ccxt).

---

## Fluxo recomendado

```
1. Instalar dependências
2. Configurar .env
3. Rodar backtest (dados históricos)
4. Rodar em paper trading (simulação ao vivo)
5. Rodar ao vivo com capital real (após validação)
```

---

## Instalação

### Requisitos
- Python 3.10+

### Passo a passo

```bash
# 1. Clone ou copie a pasta crypto-bot/
cd crypto-bot

# 2. Crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure o .env
cp .env.example .env
nano .env   # edite com suas configurações
```

---

## Configuração (.env)

| Variável | Descrição | Padrão |
|---|---|---|
| `EXCHANGE` | Exchange: `binance`, `bybit`, `kucoin` | `binance` |
| `API_KEY` | Chave da API da exchange | — |
| `API_SECRET` | Secret da API | — |
| `SYMBOL` | Par de trading | `BTC/USDT` |
| `TIMEFRAME` | Timeframe dos candles | `15m` |
| `PAPER_TRADING` | `true` = simulação, `false` = real | `true` |
| `MA_FAST` | Período da MA rápida | `7` |
| `MA_SLOW` | Período da MA lenta | `21` |
| `RSI_PERIOD` | Período do RSI | `14` |
| `RSI_OVERSOLD` | Limiar de sobrevendido | `35` |
| `RSI_OVERBOUGHT` | Limiar de sobrecomprado | `65` |
| `TRADE_SIZE_PCT` | % do saldo por trade | `20` |
| `STOP_LOSS_PCT` | Stop loss em % | `3.0` |
| `TAKE_PROFIT_PCT` | Take profit em % | `6.0` |
| `MAX_DAILY_LOSS_PCT` | Perda diária máxima em % | `10.0` |
| `TELEGRAM_ENABLED` | Ativar alertas Telegram | `false` |
| `TELEGRAM_BOT_TOKEN` | Token do bot Telegram | — |
| `TELEGRAM_CHAT_ID` | Chat ID do Telegram | — |

---

## Uso

### 1. Backtest (teste em dados históricos)

```bash
python backtest.py --symbol BTC/USDT --timeframe 1h --days 90
```

Resultado salvo em `logs/backtest_result.json`.

### 2. Paper Trading (simulação ao vivo, sem dinheiro real)

```bash
# Confirme que PAPER_TRADING=true no .env
python bot.py
```

### 3. Trading ao vivo

```bash
# No .env: PAPER_TRADING=false + API_KEY + API_SECRET preenchidos
python bot.py
```

---

## Estratégia

### Sinal de COMPRA
- MA rápida cruza MA lenta **para cima** (cruzamento altista)
- RSI abaixo do limiar de sobrevendido (`RSI_OVERSOLD`)
- **OU**: Preço abaixo da Banda de Bollinger inferior + RSI sobrevendido

### Sinal de VENDA
- MA rápida cruza MA lenta **para baixo** + RSI sobrecomprado
- **OU**: Stop loss atingido (`STOP_LOSS_PCT`)
- **OU**: Take profit atingido (`TAKE_PROFIT_PCT`)

---

## Estrutura do projeto

```
crypto-bot/
├── bot.py              # Ponto de entrada
├── backtest.py         # Backtester histórico
├── requirements.txt
├── .env.example        # Modelo de configuração
└── src/
    ├── bot.py          # Loop principal
    ├── config.py       # Carregamento de configurações
    ├── exchange.py     # Conector exchange (real + paper)
    ├── indicators.py   # RSI, SMA, Bollinger
    ├── strategy.py     # Lógica de sinais
    ├── notifier.py     # Alertas Telegram
    └── logger.py       # Logging colorido
```

---

## Segurança

- Nunca commite o arquivo `.env` com suas chaves
- Use permissões de API **somente leitura + trading** (sem saques)
- Ative whitelist de IPs na exchange quando possível
- Comece **sempre** com paper trading e valores pequenos

---

## Aviso de risco

> ⚠️ Trading de criptomoedas envolve **risco substancial de perda**. Este software é fornecido sem garantias. Teste extensivamente antes de usar capital real. O autor não se responsabiliza por perdas financeiras.
