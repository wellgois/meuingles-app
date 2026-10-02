"""Tarefas em segundo plano: lembretes do fim do teste grátis (roda a cada hora)."""
import logging
import threading
import time

from . import mailer

log = logging.getLogger("meuingles.jobs")


def send_trial_reminders(db) -> int:
    sent = 0
    base = mailer.base_url() + "app/"
    with db() as conn:
        soon = conn.execute(
            """SELECT id, name, email FROM users WHERE plan = 'trial' AND email_verified AND email IS NOT NULL
               AND reminder_2d_at IS NULL AND trial_ends_at > now() AND trial_ends_at <= now() + interval '2 days'""").fetchall()
        for u in soon:
            if mailer.send(u["email"], "Faltam 2 dias do seu teste no MeuInglês", [
                    f"Oi, {u['name'].split(' ')[0]}! Seu teste grátis do MeuInglês termina em 2 dias.",
                    "Aproveite para fazer o treino por som e uma resposta no nível 4: é onde a evolução aparece mais rápido.",
                    "Depois do teste, a assinatura vai custar R$ 29,90 por mês. Avisaremos quando ela abrir."],
                    ("Treinar agora", base)):
                conn.execute("UPDATE users SET reminder_2d_at = now() WHERE id = %s", (u["id"],)); sent += 1
        ended = conn.execute(
            """SELECT id, name, email FROM users WHERE plan = 'trial' AND email_verified AND email IS NOT NULL
               AND reminder_end_at IS NULL AND trial_ends_at <= now()""").fetchall()
        for u in ended:
            if mailer.send(u["email"], "Seu teste no MeuInglês terminou", [
                    f"Oi, {u['name'].split(' ')[0]}! Seu teste grátis de 7 dias terminou.",
                    "Seu histórico e sua evolução continuam salvos. Se quiser continuar, toque em 'Quero assinar' no app: "
                    "você será avisado assim que a assinatura de R$ 29,90 por mês abrir."],
                    ("Abrir o MeuInglês", base)):
                conn.execute("UPDATE users SET reminder_end_at = now() WHERE id = %s", (u["id"],)); sent += 1
    return sent


def start(db, every_s: int = 3600) -> None:
    def loop():
        time.sleep(30)
        while True:
            try:
                n = send_trial_reminders(db)
                if n:
                    log.info("Lembretes enviados: %s", n)
            except Exception as e:  # noqa: BLE001 - o laço nunca pode morrer
                log.warning("Falha nos lembretes: %s", e)
            time.sleep(every_s)
    threading.Thread(target=loop, daemon=True, name="trial-reminders").start()
