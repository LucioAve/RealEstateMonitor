"""
utils/notifier.py - Notifiche via Email e/o Telegram
Ogni canale è opzionale e viene attivato solo se configurato.
"""
import smtplib
import json
import urllib.request
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from .logger import get_logger

logger = get_logger("notifier")


class Notifier:
    """Gestisce l'invio di notifiche per nuovi annunci."""

    def __init__(self, config: dict):
        self.enabled  = config.get("enabled", False)
        self.email_cfg = config.get("email", {})
        self.tg_cfg    = config.get("telegram", {})

    def send(self, listings: list[dict]) -> None:
        """Invia notifiche su tutti i canali configurati."""
        if not self.enabled or not listings:
            return

        subject = f"🏠 {len(listings)} nuovi annunci – {datetime.now().strftime('%d/%m/%Y')}"
        body_html = self._build_html(listings)
        body_text = self._build_text(listings)

        if self.email_cfg.get("enabled"):
            self._send_email(subject, body_html, body_text)

        if self.tg_cfg.get("enabled"):
            self._send_telegram(body_text)

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------

    def _send_email(self, subject: str, html: str, text: str) -> None:
        cfg = self.email_cfg
        required = ["smtp_host", "smtp_port", "username", "password", "from", "to"]
        if not all(cfg.get(k) for k in required):
            logger.warning("Email non configurata correttamente, skip.")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["from"]
        msg["To"]      = cfg["to"]
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html",  "utf-8"))

        try:
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
                server.ehlo()
                server.starttls()
                server.login(cfg["username"], cfg["password"])
                server.sendmail(cfg["from"], cfg["to"], msg.as_string())
            logger.info(f"Email inviata a {cfg['to']}")
        except Exception as e:
            logger.error(f"Errore invio email: {e}")

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def _send_telegram(self, text: str) -> None:
        cfg = self.tg_cfg
        token   = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")

        if not token or not chat_id:
            logger.warning("Telegram non configurato, skip.")
            return

        # Telegram limita i messaggi a 4096 caratteri
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        for chunk in chunks:
            params = urllib.parse.urlencode({
                "chat_id":    chat_id,
                "text":       chunk,
                "parse_mode": "HTML",
            }).encode()
            try:
                req = urllib.request.Request(url, data=params, method="POST")
                urllib.request.urlopen(req, timeout=10)
                logger.info("Messaggio Telegram inviato.")
            except Exception as e:
                logger.error(f"Errore invio Telegram: {e}")

    # ------------------------------------------------------------------
    # Formatter
    # ------------------------------------------------------------------

    def _build_text(self, listings: list[dict]) -> str:
        lines = [f"🏠 NUOVI ANNUNCI – {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"]
        for i, l in enumerate(listings, 1):
            price = l.get("price", "N/D")
            lines.append(
                f"\n{i}. {l.get('title', 'Senza titolo')}\n"
                f"   💶 {price}  📍 {l.get('location', 'N/D')}\n"
                f"   🔗 {l.get('url', '')}\n"
            )
        return "\n".join(lines)

    def _build_html(self, listings: list[dict]) -> str:
        rows = ""
        for l in listings:
            rows += f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #eee;">
                <a href="{l.get('url','')}" style="font-weight:bold;color:#1a73e8;text-decoration:none;">
                  {l.get('title','N/D')}
                </a><br>
                <small style="color:#666;">📍 {l.get('location','N/D')} – 📅 {l.get('date','')}</small>
              </td>
              <td style="padding:8px;border-bottom:1px solid #eee;font-weight:bold;white-space:nowrap;">
                {l.get('price','N/D')}
              </td>
            </tr>"""

        return f"""
        <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;">
          <h2 style="color:#1a73e8;">🏠 Nuovi annunci rilevati</h2>
          <p style="color:#666;">{datetime.now().strftime('%d/%m/%Y alle %H:%M')}</p>
          <table width="100%" cellspacing="0" style="border-collapse:collapse;">
            <thead>
              <tr style="background:#f5f5f5;">
                <th style="padding:10px;text-align:left;">Annuncio</th>
                <th style="padding:10px;text-align:left;">Prezzo</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </body></html>"""
