#!/usr/bin/env python3
"""
deploy.py — Envia o projeto do seu PC Windows para o servidor VPS

Uso:
    python deploy.py --ip IP_DO_SERVIDOR --user ubuntu --key caminho/para/chave.pem

Exemplos:
    # Com chave SSH (Hetzner, Oracle, DigitalOcean)
    python deploy.py --ip 123.45.67.89 --key C:/Users/Bruno/chave.pem

    # Com senha (DigitalOcean sem chave SSH)
    python deploy.py --ip 123.45.67.89 --user root --password

O script:
    1. Verifica a conexão com o servidor
    2. Envia todos os arquivos do projeto
    3. Instala as dependências
    4. Reinicia o bot se já estiver rodando
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(cmd: str, check=True, capture=False):
    result = subprocess.run(
        cmd, shell=True, check=check,
        capture_output=capture, text=True
    )
    return result


def ssh_cmd(ip, user, key, cmd, password=None):
    if key:
        return f'ssh -i "{key}" -o StrictHostKeyChecking=no {user}@{ip} "{cmd}"'
    return f'ssh -o StrictHostKeyChecking=no {user}@{ip} "{cmd}"'


def scp_cmd(ip, user, key, local, remote):
    if key:
        return f'scp -i "{key}" -o StrictHostKeyChecking=no -r "{local}" {user}@{ip}:{remote}'
    return f'scp -o StrictHostKeyChecking=no -r "{local}" {user}@{ip}:{remote}'


def main():
    parser = argparse.ArgumentParser(description="Deploy CryptoCoin Bot para VPS")
    parser.add_argument("--ip",       required=True,          help="IP do servidor")
    parser.add_argument("--user",     default="ubuntu",        help="Usuário SSH (padrão: ubuntu)")
    parser.add_argument("--key",      default=None,            help="Caminho da chave .pem")
    parser.add_argument("--dir",      default=".",             help="Pasta do projeto (padrão: pasta atual)")
    parser.add_argument("--remote",   default="/home/cryptobot/bot", help="Pasta remota")
    parser.add_argument("--no-restart", action="store_true",  help="Não reinicia o bot após deploy")
    args = parser.parse_args()

    print("\n🚀 CryptoCoin Bot — Deploy para VPS")
    print("=" * 45)
    print(f"  Servidor:  {args.user}@{args.ip}")
    print(f"  Pasta:     {args.dir} → {args.remote}")
    if args.key:
        print(f"  Chave SSH: {args.key}")
    print()

    project_dir = Path(args.dir).resolve()

    # ── 1. Verifica conexão ───────────────────────────────────────────────────
    print("1. Verificando conexão com o servidor...")
    test = run(ssh_cmd(args.ip, args.user, args.key, "echo OK"), check=False, capture=True)
    if "OK" not in test.stdout:
        print(f"   ❌ Não foi possível conectar: {test.stderr}")
        print("   Verifique o IP, usuário e chave SSH.")
        sys.exit(1)
    print("   ✅ Conexão OK")

    # ── 2. Garante que a pasta remota existe ──────────────────────────────────
    print("2. Preparando pasta remota...")
    run(ssh_cmd(args.ip, args.user, args.key,
        f"sudo mkdir -p {args.remote}/logs && sudo chown -R {args.user}:{args.user} {args.remote}"))
    print(f"   ✅ Pasta {args.remote} pronta")

    # ── 3. Para o bot se estiver rodando ──────────────────────────────────────
    print("3. Parando bot (se estiver rodando)...")
    run(ssh_cmd(args.ip, args.user, args.key,
        "sudo systemctl stop cryptobot 2>/dev/null || true"), check=False)
    print("   ✅ Bot parado")

    # ── 4. Envia arquivos (exclui .venv, __pycache__, logs) ───────────────────
    print("4. Enviando arquivos do projeto...")

    # Lista de arquivos/pastas a enviar
    to_send = [
        "bot.py", "backtest.py", "autotune.py", "scheduler.py",
        "requirements.txt", "dashboard.html", "AUTOTUNE.md", "README.md",
        "src/", "install.sh",
    ]

    # .env só envia se não existir no servidor
    env_exists = run(
        ssh_cmd(args.ip, args.user, args.key, f"test -f {args.remote}/.env && echo yes || echo no"),
        capture=True, check=False
    ).stdout.strip()

    sent = 0
    for item in to_send:
        local_path = project_dir / item
        if not local_path.exists():
            print(f"   ⚠️  {item} não encontrado — pulando")
            continue
        result = run(scp_cmd(args.ip, args.user, args.key, str(local_path), args.remote + "/"), check=False)
        if result.returncode == 0:
            sent += 1
        else:
            print(f"   ⚠️  Erro ao enviar {item}")

    if env_exists == "no":
        env_path = project_dir / ".env.example"
        if env_path.exists():
            run(scp_cmd(args.ip, args.user, args.key, str(env_path), args.remote + "/.env"))
            print("   📄 .env.example copiado como .env — configure antes de iniciar!")
    else:
        print("   🔒 .env já existe no servidor — mantido sem alteração")

    print(f"   ✅ {sent} itens enviados")

    # ── 5. Instala/atualiza dependências ──────────────────────────────────────
    print("5. Instalando dependências Python...")
    run(ssh_cmd(args.ip, args.user, args.key,
        f"cd {args.remote} && "
        f"python3.11 -m venv .venv 2>/dev/null || true && "
        f".venv/bin/pip install --upgrade pip -q && "
        f".venv/bin/pip install -r requirements.txt -q"
    ))
    print("   ✅ Dependências instaladas")

    # ── 6. Ajusta permissões ──────────────────────────────────────────────────
    print("6. Ajustando permissões...")
    run(ssh_cmd(args.ip, args.user, args.key,
        f"sudo chown -R cryptobot:cryptobot {args.remote} 2>/dev/null || "
        f"chown -R {args.user}:{args.user} {args.remote} && "
        f"chmod 600 {args.remote}/.env 2>/dev/null || true && "
        f"chmod +x {args.remote}/install.sh 2>/dev/null || true"
    ))
    print("   ✅ Permissões ajustadas")

    # ── 7. Reinicia o bot ─────────────────────────────────────────────────────
    if not args.no_restart:
        print("7. Reiniciando o bot...")
        result = run(
            ssh_cmd(args.ip, args.user, args.key, "sudo systemctl start cryptobot"),
            check=False, capture=True
        )
        if result.returncode == 0:
            print("   ✅ Bot iniciado com sucesso!")
        else:
            print("   ⚠️  Não foi possível iniciar o bot automaticamente.")
            print(f"      Conecte ao servidor e rode: sudo systemctl start cryptobot")
    else:
        print("7. Deploy sem reiniciar (--no-restart)")

    # ── Resumo ────────────────────────────────────────────────────────────────
    print()
    print("=" * 45)
    print("✅ DEPLOY CONCLUÍDO!")
    print()
    print("Próximos passos:")
    print(f"  ssh {args.user}@{args.ip}")
    print(f"  nano {args.remote}/.env          # configura se necessário")
    print(f"  bot-status                        # verifica o status")
    print(f"  bot-logs                          # acompanha os logs")
    print()


if __name__ == "__main__":
    main()
