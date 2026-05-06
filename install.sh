#!/bin/bash
# =============================================================================
#  CryptoCoin Bot — Script de instalação automática
#  Testado em: Ubuntu 22.04 LTS (Hetzner, DigitalOcean, Oracle Cloud)
#
#  Uso:
#    chmod +x install.sh && sudo ./install.sh
#
#  O que este script faz:
#    1. Atualiza o sistema
#    2. Instala Python 3.11 e dependências
#    3. Cria usuário dedicado 'cryptobot'
#    4. Faz upload e configura o projeto
#    5. Cria serviço systemd (reinicia automaticamente)
#    6. Configura firewall básico
#    7. Configura rotação de logs automática
#    8. Instala monitoramento de memória/CPU
# =============================================================================

set -e  # Para em qualquer erro

# ── Cores para output ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()     { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
section() { echo -e "\n${CYAN}══════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}══════════════════════════════════════${NC}"; }

# ── Verifica se é root ────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Execute como root: sudo ./install.sh"
fi

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}"
echo "  ██████╗██████╗ ██╗   ██╗██████╗ ████████╗ ██████╗ "
echo " ██╔════╝██╔══██╗╚██╗ ██╔╝██╔══██╗╚══██╔══╝██╔═══██╗"
echo " ██║     ██████╔╝ ╚████╔╝ ██████╔╝   ██║   ██║   ██║"
echo " ██║     ██╔══██╗  ╚██╔╝  ██╔═══╝    ██║   ██║   ██║"
echo " ╚██████╗██║  ██║   ██║   ██║        ██║   ╚██████╔╝"
echo "  ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚═╝        ╚═╝    ╚═════╝ "
echo -e "${NC}"
echo -e "  ${GREEN}Bot de Trading — Instalador Automático v4.0${NC}"
echo -e "  Ubuntu 22.04 LTS\n"

# ── Detecta provedor ──────────────────────────────────────────────────────────
PROVIDER="desconhecido"
if curl -s --max-time 2 http://169.254.169.254/opc/v1/instance/ &>/dev/null; then
    PROVIDER="oracle"
elif curl -s --max-time 2 http://169.254.169.254/hetzner/v1/metadata/ &>/dev/null; then
    PROVIDER="hetzner"
elif curl -s --max-time 2 http://169.254.169.254/metadata/v1/ &>/dev/null; then
    PROVIDER="digitalocean"
fi
log "Provedor detectado: $PROVIDER"

# ── Configurações ─────────────────────────────────────────────────────────────
BOT_USER="cryptobot"
BOT_DIR="/home/$BOT_USER/bot"
SERVICE_NAME="cryptobot"
PYTHON_VERSION="3"

section "1/8 — Atualizando o sistema"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip vim htop \
    software-properties-common \
    build-essential libssl-dev libffi-dev \
    python3-dev python3-pip python3-venv \
    logrotate ufw fail2ban
log "Sistema atualizado"

# ── Python 3.11 ───────────────────────────────────────────────────────────────
section "2/8 — Instalando Python $PYTHON_VERSION"
add-apt-repository -y ppa:deadsnakes/ppa -q 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-dev
##update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
log "Python $(python3 --version) instalado"

section "3/8 — Criando usuário dedicado '$BOT_USER'"
if id "$BOT_USER" &>/dev/null; then
    warn "Usuário $BOT_USER já existe — pulando criação"
else
    useradd -m -s /bin/bash "$BOT_USER"
    log "Usuário $BOT_USER criado"
fi

# ── Cria estrutura de diretórios ──────────────────────────────────────────────
mkdir -p "$BOT_DIR"
mkdir -p "$BOT_DIR/logs"
mkdir -p "/var/log/cryptobot"
chown -R "$BOT_USER:$BOT_USER" "$BOT_DIR"
chown -R "$BOT_USER:$BOT_USER" "/var/log/cryptobot"
log "Diretórios criados em $BOT_DIR"

section "4/8 — Configurando ambiente Python"
sudo -u "$BOT_USER" python3 -m venv "$BOT_DIR/.venv"
log "Ambiente virtual criado"

# Cria requirements se não existir
if [ ! -f "$BOT_DIR/requirements.txt" ]; then
cat > "$BOT_DIR/requirements.txt" << 'EOF'
ccxt>=4.3.0
pandas>=2.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
EOF
fi

sudo -u "$BOT_USER" "$BOT_DIR/.venv/bin/pip" install --upgrade pip -q
sudo -u "$BOT_USER" "$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt" -q
log "Dependências instaladas"

section "5/8 — Criando serviço systemd"
cat > "/etc/systemd/system/$SERVICE_NAME.service" << EOF
[Unit]
Description=CryptoCoin Trading Bot v4
Documentation=https://github.com/seu-usuario/cryptocoin
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=5

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/.venv/bin/python bot.py
ExecStop=/bin/kill -SIGTERM \$MAINPID

# Reinicia automaticamente se travar
Restart=always
RestartSec=30

# Variáveis de ambiente
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

# Logs
StandardOutput=append:/var/log/cryptobot/stdout.log
StandardError=append:/var/log/cryptobot/stderr.log

# Limites de segurança
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$BOT_DIR /var/log/cryptobot

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
log "Serviço systemd criado e habilitado"

section "6/8 — Configurando firewall (UFW)"
ufw --force reset > /dev/null
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
ufw allow ssh > /dev/null
ufw allow 22/tcp > /dev/null
# Abre porta 8765 para o dashboard (opcional — só se quiser acesso externo)
# ufw allow 8765/tcp > /dev/null
ufw --force enable > /dev/null
log "Firewall configurado — SSH permitido, resto bloqueado"

# ── Fail2ban para proteger SSH ─────────────────────────────────────────────────
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = /var/log/auth.log
EOF
systemctl enable fail2ban > /dev/null
systemctl restart fail2ban > /dev/null
log "Fail2ban configurado — proteção contra força bruta SSH"

section "7/8 — Configurando rotação de logs"
cat > /etc/logrotate.d/cryptobot << 'EOF'
/var/log/cryptobot/*.log
/home/cryptobot/bot/logs/*.log
/home/cryptobot/bot/logs/*.jsonl
{
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d
}
EOF
log "Rotação de logs configurada — mantém 30 dias, comprime automaticamente"

section "8/8 — Scripts de gerenciamento"

# ── Script de status ──────────────────────────────────────────────────────────
cat > /usr/local/bin/bot-status << 'SCRIPT'
#!/bin/bash
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  CryptoCoin Bot — Status${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# Status do serviço
STATUS=$(systemctl is-active cryptobot)
if [ "$STATUS" = "active" ]; then
    echo -e "  Status:    ${GREEN}● RODANDO${NC}"
else
    echo -e "  Status:    ${RED}● PARADO${NC}"
fi

# Uptime do serviço
STARTED=$(systemctl show cryptobot --property=ActiveEnterTimestamp | cut -d= -f2)
echo -e "  Iniciado:  $STARTED"

# PID e uso de recursos
PID=$(systemctl show cryptobot --property=MainPID | cut -d= -f2)
if [ "$PID" != "0" ] && [ -n "$PID" ]; then
    CPU=$(ps -p $PID -o %cpu --no-headers 2>/dev/null | tr -d ' ')
    MEM=$(ps -p $PID -o %mem --no-headers 2>/dev/null | tr -d ' ')
    RSS=$(ps -p $PID -o rss --no-headers 2>/dev/null | tr -d ' ')
    RSS_MB=$((${RSS:-0} / 1024))
    echo -e "  PID:       $PID"
    echo -e "  CPU:       ${CPU}%"
    echo -e "  Memória:   ${MEM}% (~${RSS_MB}MB)"
fi

# Espaço em disco
DISK=$(df -h /home/cryptobot/bot/logs 2>/dev/null | tail -1 | awk '{print $3"/"$2" ("$5" usado)"}')
echo -e "  Disco:     $DISK"

# Últimas linhas do log
echo -e "\n${CYAN}━━━ Últimas 10 linhas do log ━━━${NC}"
tail -10 /home/cryptobot/bot/logs/bot.log 2>/dev/null || echo "  (sem logs ainda)"

# Último trade
echo -e "\n${CYAN}━━━ Último trade ━━━${NC}"
tail -1 /home/cryptobot/bot/logs/trades.jsonl 2>/dev/null | python3 -c "
import sys,json
try:
    t=json.load(sys.stdin)
    pnl=t.get('pnl')
    pnl_str=f'+\${pnl:.2f}' if pnl and pnl>0 else (f'\${pnl:.2f}' if pnl else 'N/A')
    print(f'  {t[\"side\"]} | \${t[\"price\"]:,.2f} | {t[\"timestamp\"][:16]} | P&L: {pnl_str}')
except:
    print('  Nenhum trade registrado ainda')
"
echo ""
SCRIPT
chmod +x /usr/local/bin/bot-status

# ── Script de logs ao vivo ────────────────────────────────────────────────────
cat > /usr/local/bin/bot-logs << 'SCRIPT'
#!/bin/bash
echo "Acompanhando logs do bot (Ctrl+C para sair)..."
tail -f /home/cryptobot/bot/logs/bot.log 2>/dev/null || \
journalctl -u cryptobot -f --no-pager
SCRIPT
chmod +x /usr/local/bin/bot-logs

# ── Script de atualização ─────────────────────────────────────────────────────
cat > /usr/local/bin/bot-update << 'SCRIPT'
#!/bin/bash
BOT_DIR="/home/cryptobot/bot"
echo "Parando o bot..."
systemctl stop cryptobot
echo "Fazendo backup dos logs e .env..."
cp "$BOT_DIR/.env" /tmp/.env.backup 2>/dev/null
echo "Pronto para receber novo zip. Copie o arquivo e extraia em $BOT_DIR"
echo "Depois execute: systemctl start cryptobot"
SCRIPT
chmod +x /usr/local/bin/bot-update

# ── Script de backup ──────────────────────────────────────────────────────────
cat > /usr/local/bin/bot-backup << 'SCRIPT'
#!/bin/bash
BOT_DIR="/home/cryptobot/bot"
BACKUP_DIR="/home/cryptobot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/bot_backup_$DATE.tar.gz" \
    "$BOT_DIR/logs/" \
    "$BOT_DIR/.env" \
    2>/dev/null
# Mantém só os últimos 7 backups
ls -t "$BACKUP_DIR"/bot_backup_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null
echo "Backup salvo em $BACKUP_DIR/bot_backup_$DATE.tar.gz"
SCRIPT
chmod +x /usr/local/bin/bot-backup

# ── Cron para backup diário ───────────────────────────────────────────────────
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/bot-backup >> /var/log/cryptobot/backup.log 2>&1") | crontab -
log "Backup automático configurado — roda todo dia às 2h"

# ── Cria .env padrão se não existir ──────────────────────────────────────────
if [ ! -f "$BOT_DIR/.env" ]; then
cat > "$BOT_DIR/.env" << 'EOF'
# ── Exchange ──────────────────────────────────────────────────
EXCHANGE=binance
API_KEY=SUA_API_KEY_AQUI
API_SECRET=SEU_API_SECRET_AQUI

# ── Par / Timeframe ───────────────────────────────────────────
SYMBOL=BTC/USDT
TIMEFRAME=1h

# ── Modo ──────────────────────────────────────────────────────
PAPER_TRADING=true
PAPER_INITIAL_BALANCE=10000

# ── Estratégia ────────────────────────────────────────────────
MA_FAST=7
MA_SLOW=21
RSI_PERIOD=14
RSI_OVERSOLD=35
RSI_OVERBOUGHT=65
BB_PERIOD=20
BB_STD=2.0

# ── Risco ─────────────────────────────────────────────────────
TRADE_SIZE_PCT=20
STOP_LOSS_PCT=3.0
TAKE_PROFIT_PCT=6.0
MAX_OPEN_TRADES=1
MAX_DAILY_LOSS_PCT=10.0

# ── Telegram ──────────────────────────────────────────────────
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── Logs ──────────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
EOF
chown "$BOT_USER:$BOT_USER" "$BOT_DIR/.env"
chmod 600 "$BOT_DIR/.env"
warn ".env criado com valores padrão — edite antes de iniciar!"
fi

# ── Resumo final ──────────────────────────────────────────────────────────────
SERVER_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     INSTALAÇÃO CONCLUÍDA COM SUCESSO! ✅     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}IP do servidor:${NC}  $SERVER_IP"
echo -e "  ${CYAN}Pasta do bot:${NC}    $BOT_DIR"
echo -e "  ${CYAN}Logs:${NC}            $BOT_DIR/logs/"
echo ""
echo -e "${YELLOW}━━━ PRÓXIMOS PASSOS ━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}1.${NC} Envie o projeto para o servidor:"
echo -e "     ${CYAN}scp -r CryptoCoin/* ubuntu@$SERVER_IP:$BOT_DIR/${NC}"
echo ""
echo -e "  ${GREEN}2.${NC} Configure o .env:"
echo -e "     ${CYAN}nano $BOT_DIR/.env${NC}"
echo ""
echo -e "  ${GREEN}3.${NC} Inicie o bot:"
echo -e "     ${CYAN}systemctl start cryptobot${NC}"
echo ""
echo -e "  ${GREEN}4.${NC} Veja o status:"
echo -e "     ${CYAN}bot-status${NC}"
echo ""
echo -e "  ${GREEN}5.${NC} Acompanhe os logs ao vivo:"
echo -e "     ${CYAN}bot-logs${NC}"
echo ""
echo -e "${YELLOW}━━━ COMANDOS ÚTEIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${CYAN}bot-status${NC}              Ver status, CPU, memória e último trade"
echo -e "  ${CYAN}bot-logs${NC}               Logs ao vivo"
echo -e "  ${CYAN}bot-backup${NC}             Fazer backup manual"
echo -e "  ${CYAN}bot-update${NC}             Preparar atualização"
echo ""
echo -e "  ${CYAN}systemctl start cryptobot${NC}    Iniciar"
echo -e "  ${CYAN}systemctl stop cryptobot${NC}     Parar"
echo -e "  ${CYAN}systemctl restart cryptobot${NC}  Reiniciar"
echo -e "  ${CYAN}systemctl status cryptobot${NC}   Status detalhado"
echo ""
