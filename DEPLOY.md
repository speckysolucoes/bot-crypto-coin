# Guia de Deploy — CryptoCoin Bot

## Sequência completa do zero ao servidor rodando

---

## Passo 1 — Criar o servidor

### Opção A — Hetzner (€4/mês, recomendado)

1. Acesse **hetzner.com/cloud** e crie uma conta
2. Clique em **New Server**
3. Escolha:
   - Localização: **Nuremberg** ou **Falkenstein**
   - Sistema: **Ubuntu 22.04**
   - Tipo: **CX22** (2 vCPU, 4GB RAM — suficiente)
   - SSH Key: clique em **Add SSH Key** e cole sua chave pública
4. Clique em **Create & Buy**
5. Anote o IP do servidor

### Opção B — DigitalOcean ($6/mês, mais fácil)

1. Acesse **digitalocean.com** e crie uma conta
2. Clique em **Create → Droplets**
3. Escolha:
   - Região: **Frankfurt** ou **New York**
   - Sistema: **Ubuntu 22.04 LTS**
   - Plano: **Basic → Regular → $6/mo**
   - Autenticação: **SSH Key** (recomendado) ou **Password**
4. Clique em **Create Droplet**
5. Anote o IP

### Opção C — Oracle Cloud (GRÁTIS)

1. Acesse **cloud.oracle.com** e crie conta (pede cartão mas não cobra)
2. Vá em **Compute → Instances → Create Instance**
3. Escolha:
   - Image: **Ubuntu 22.04**
   - Shape: **VM.Standard.A1.Flex** (Always Free)
   - OCPUs: 4, Memory: 24GB
4. Baixe a chave privada gerada
5. Anote o IP público

---

## Passo 2 — Gerar chave SSH (se não tiver)

No PowerShell do seu Windows:

```powershell
# Gera um par de chaves SSH
ssh-keygen -t ed25519 -C "cryptocoin-bot"

# Mostra a chave pública (copie para o painel do servidor)
cat C:\Users\SeuNome\.ssh\id_ed25519.pub
```

---

## Passo 3 — Conectar ao servidor

```powershell
# Com chave SSH (Hetzner/Oracle/DigitalOcean com chave)
ssh ubuntu@IP_DO_SERVIDOR

# Com senha (DigitalOcean sem chave)
ssh root@IP_DO_SERVIDOR
```

---

## Passo 4 — Rodar o instalador no servidor

Após conectar via SSH, copie e cole no terminal do servidor:

```bash
# Baixa e roda o instalador
curl -o install.sh https://raw.githubusercontent.com/seu-usuario/cryptocoin/main/install.sh
# OU: copie o arquivo install.sh manualmente (veja Passo 5)
chmod +x install.sh && sudo ./install.sh
```

---

## Passo 5 — Enviar o projeto do seu PC para o servidor

No PowerShell do Windows, dentro da pasta CryptoCoin:

```powershell
# Envia tudo automaticamente
python deploy.py --ip IP_DO_SERVIDOR --user ubuntu --key C:\Users\SeuNome\.ssh\id_ed25519

# Sem chave SSH (com senha — vai pedir a senha)
python deploy.py --ip IP_DO_SERVIDOR --user root
```

O script deploy.py faz tudo automaticamente:
- Para o bot se estiver rodando
- Envia todos os arquivos
- Instala as dependências
- Reinicia o bot

---

## Passo 6 — Configurar o .env no servidor

```bash
# No servidor, edita o .env
nano /home/cryptobot/bot/.env

# Campos obrigatórios para começar:
# PAPER_TRADING=true        (mantenha true por enquanto)
# SYMBOL=BTC/USDT
# TIMEFRAME=1h

# Salva: Ctrl+O → Enter → Ctrl+X
```

---

## Passo 7 — Iniciar o bot

```bash
# Inicia
sudo systemctl start cryptobot

# Verifica status (mostra CPU, memória, último trade)
bot-status

# Acompanha logs ao vivo
bot-logs
```

---

## Comandos do dia a dia

```bash
# Status completo com métricas
bot-status

# Logs ao vivo
bot-logs

# Backup manual
bot-backup

# Parar o bot
sudo systemctl stop cryptobot

# Reiniciar o bot
sudo systemctl restart cryptobot

# Ver erros
sudo journalctl -u cryptobot -n 50

# Rodar backtest no servidor
cd /home/cryptobot/bot
sudo -u cryptobot .venv/bin/python backtest.py

# Rodar auto-tuner manualmente
sudo -u cryptobot .venv/bin/python autotune.py

# Editar configurações
nano /home/cryptobot/bot/.env
# Após editar: sudo systemctl restart cryptobot
```

---

## Atualizar o bot (quando sair nova versão)

No Windows, dentro da pasta CryptoCoin com as novidades:

```powershell
python deploy.py --ip IP_DO_SERVIDOR --user ubuntu --key chave.pem
```

O deploy.py cuida de parar o bot, enviar os novos arquivos e reiniciar.

---

## Monitoramento de recursos

```bash
# CPU e memória em tempo real
htop

# Espaço em disco
df -h

# Quanto os logs estão ocupando
du -sh /home/cryptobot/bot/logs/

# Ver todos os serviços rodando
sudo systemctl list-units --type=service --state=running
```

---

## Solução de problemas comuns

### Bot não inicia
```bash
# Ver o erro exato
sudo journalctl -u cryptobot -n 30

# Testar manualmente (mostra erro na tela)
cd /home/cryptobot/bot
sudo -u cryptobot .venv/bin/python bot.py
```

### Erro de API key
```bash
# Verifique se o .env está correto
cat /home/cryptobot/bot/.env | grep API
# (não compartilhe essa saída com ninguém)
```

### Sem espaço em disco
```bash
# Ver o que está ocupando espaço
du -sh /home/cryptobot/bot/logs/*
# Limpar logs antigos manualmente
sudo logrotate -f /etc/logrotate.d/cryptobot
```

### Bot reinicia em loop
```bash
# Ver quantas vezes reiniciou
sudo systemctl status cryptobot
# Ver o erro que causa o restart
sudo journalctl -u cryptobot -n 50 --no-pager
```
