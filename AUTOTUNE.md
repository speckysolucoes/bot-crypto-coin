# Auto-Tuner — Aprendizado Automático de Parâmetros

## O que é

O auto-tuner usa um **algoritmo genético** para encontrar os melhores parâmetros da estratégia automaticamente, testando centenas de combinações em dados históricos e evoluindo as melhores ao longo de gerações.

Ele roda **toda semana às 3h da manhã** sem você precisar fazer nada.

---

## Como funciona (passo a passo)

```
Semana 1:  Bot opera com parâmetros iniciais do .env
           ↓
Domingo 3h: Auto-tuner acorda
           ↓
           Baixa 74 dias de dados (60 treino + 14 validação)
           ↓
Geração 1: [MA 7/21, RSI 35/65] fitness: +12%
           [MA 9/26, RSI 30/70] fitness: +18%  ← sobrevive
           [MA 5/18, RSI 40/60] fitness: -3%   ← descartado
           ↓
Geração 2: filhos com mutações dos sobreviventes...
           ↓
Geração 25: parâmetros otimizados para as condições recentes
           ↓
           Valida em 14 dias que NÃO foram usados no treino
           ↓
           Se passar: atualiza .env e recarrega o bot
           Se falhar: mantém parâmetros anteriores
```

---

## Uso manual

```bash
# Rodar otimização agora (atualiza o .env)
python autotune.py

# Testar sem alterar o .env
python autotune.py --dry-run

# Customizar períodos e intensidade
python autotune.py --train-days 90 --val-days 21 --generations 50 --population 60

# Exigir retorno mínimo de 2% na validação antes de aceitar
python autotune.py --min-val 2.0
```

## Parâmetros do autotune.py

| Flag | Descrição | Padrão |
|---|---|---|
| `--train-days` | Dias usados para treinar | 60 |
| `--val-days` | Dias usados para validar | 14 |
| `--population` | Tamanho da população genética | 40 |
| `--generations` | Número de gerações | 25 |
| `--min-val` | Retorno mínimo na validação (%) | 0.0 |
| `--dry-run` | Não altera o .env | false |

---

## Arquivos gerados

| Arquivo | Conteúdo |
|---|---|
| `logs/autotune_history.jsonl` | Histórico de todas as otimizações |
| `logs/optimization_history.json` | Evolução do fitness por geração |
| `logs/schedule_state.json` | Quando foi a última otimização |

---

## Configurar frequência e horário

No arquivo `src/bot.py`, dentro do `__init__` do `TradingBot`:

```python
self.scheduler = WeeklyScheduler(
    interval_days=7,   # A cada quantos dias otimizar
    run_hour=3,        # Hora do dia (0-23) para rodar
    train_days=60,     # Dias de dados para treino
    val_days=14,       # Dias para validação
    population=40,     # Tamanho da população
    generations=25,    # Gerações do algoritmo genético
    min_val_return=0.0 # Retorno mínimo para aceitar novos params
)
```

---

## Proteções contra overfitting

O auto-tuner divide os dados em dois conjuntos separados:

- **Treino (60 dias):** o algoritmo genético otimiza aqui
- **Validação (14 dias):** testa os parâmetros em dados que nunca viu

Se os parâmetros forem bons só no treino mas ruins na validação, eles são **rejeitados** automaticamente e o bot continua com os parâmetros anteriores. Isso evita que o bot seja "decoreba" do passado e falhe no presente.
