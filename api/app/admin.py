"""Comandos de administração (rodar dentro do container):

    docker compose exec api python -m app.admin dono      -> cria a conta do dono e junta os treinos antigos nela
    docker compose exec api python -m app.admin testar-email voce@exemplo.com
    docker compose exec api python -m app.admin avisar-assinatura   -> avisa a lista "Quero assinar"
"""
import getpass
import sys

from . import auth, mailer
from .main import db


def dono():
    with db() as conn:
        legacy = conn.execute(
            """SELECT u.id, u.name, count(a.id) AS n FROM users u LEFT JOIN attempts a ON a.user_id = u.id
               WHERE u.email IS NULL GROUP BY u.id ORDER BY n DESC""").fetchall()
    print(f"Contas antigas (do código de acesso): {len(legacy)}")
    for u in legacy:
        print(f"  {u['name']}: {u['n']} treinos")
    email = input("Seu e-mail de login: ").strip().lower()
    if not auth.valid_email(email):
        sys.exit("E-mail inválido.")
    pw = getpass.getpass("Crie uma senha (mínimo 8 caracteres, não aparece na tela): ")
    if len(pw) < 8 or pw != getpass.getpass("Repita a senha: "):
        sys.exit("Senha curta ou diferente na repetição. Nada foi alterado.")
    with db() as conn:
        with conn.transaction():
            exists = conn.execute("SELECT id FROM users WHERE lower(email) = %s", (email,)).fetchone()
            if exists:
                owner = exists["id"]
            elif legacy:
                owner = legacy[0]["id"]
            else:
                import uuid
                owner = uuid.uuid4()
                conn.execute("INSERT INTO users (id, name) VALUES (%s, %s)", (owner, input("Seu nome: ").strip() or "Dono"))
            conn.execute("""UPDATE users SET email = %s, pass_hash = %s, email_verified = true, plan = 'owner',
                            is_admin = true, terms_accepted_at = now() WHERE id = %s""",
                         (email, auth.hash_password(pw), owner))
            others = [u["id"] for u in legacy if u["id"] != owner]
            for old in others:
                conn.execute("UPDATE attempts SET user_id = %s WHERE user_id = %s", (owner, old))
                conn.execute("""INSERT INTO review_items (user_id, word, interval_days, next_due, misses, hits)
                                SELECT %s, word, interval_days, next_due, misses, hits FROM review_items WHERE user_id = %s
                                ON CONFLICT (user_id, word) DO NOTHING""", (owner, old))
                conn.execute("DELETE FROM users WHERE id = %s", (old,))
            n = conn.execute("SELECT count(*) AS n FROM attempts WHERE user_id = %s", (owner,)).fetchone()["n"]
    print(f"Pronto: conta do dono {email} com {n} treinos. {len(others)} conta(s) antiga(s) foram juntadas a ela.")


def testar_email(to: str):
    if not mailer.configured():
        sys.exit("E-mail não configurado: faltam SMTP_HOST, SMTP_USER, SMTP_PASSWORD ou MAIL_FROM no .env.")
    ok = mailer.send(to, "Teste de e-mail do MeuInglês", ["Se você está lendo isto, o envio pelo Brevo está funcionando."])
    print("Enviado. Confira a caixa de entrada e o spam." if ok else "Falhou. Veja o aviso acima.")


def avisar_assinatura():
    if not mailer.configured():
        sys.exit("E-mail não configurado.")
    with db() as conn:
        rows = conn.execute("""SELECT id, name, email FROM users WHERE wants_subscription_at IS NOT NULL
                               AND email_verified AND plan NOT IN ('active', 'owner')""").fetchall()
    print(f"Pessoas na lista 'Quero assinar' sem assinatura: {len(rows)}")
    if not rows or input("Enviar o aviso agora? (s/N) ").strip().lower() != "s":
        print("Nada foi enviado."); return
    sent = 0
    for u in rows:
        if mailer.send(u["email"], "A assinatura do MeuInglês abriu", [
                f"Oi, {u['name'].split(' ')[0]}! Você pediu para ser avisado: a assinatura do MeuInglês já está disponível.",
                "São R$ 29,90 por mês pelo Mercado Pago, com até 300 minutos de pronúncia avaliada e cancelamento no próprio app."],
                ("Assinar agora", mailer.base_url() + "app/")):
            sent += 1
    with db() as conn:
        conn.execute("UPDATE users SET wants_subscription_at = NULL WHERE id = ANY(%s)", ([u["id"] for u in rows],))
    print(f"Avisos enviados: {sent}.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "dono":
        dono()
    elif cmd == "testar-email" and len(sys.argv) > 2:
        testar_email(sys.argv[2])
    elif cmd == "avisar-assinatura":
        avisar_assinatura()
    else:
        print(__doc__)
