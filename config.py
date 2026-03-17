"""
Configuration — modifie ce fichier pour ajouter tes salles de sport et ton email.

COMMENT AJOUTER UNE SALLE :
1. Donne-moi l'URL du planning de la salle dans Claude
2. Je génère automatiquement les sélecteurs CSS pour toi
3. Tu copies-colles le bloc dans la liste GYMS ci-dessous
"""

# ── Salles de sport à tracker ─────────────────────────────────────────────────
# Chaque salle est un dictionnaire avec les champs suivants :
#
#   id                 : identifiant unique (pas d'espaces, pas d'accents)
#   name               : nom affiché dans le dashboard et les emails
#   url                : URL du planning public
#   session_selector   : sélecteur CSS du bloc qui contient UNE séance
#   title_selector     : sélecteur CSS du nom de la séance (dans le bloc)
#   coach_selector     : sélecteur CSS du nom du coach (dans le bloc)
#   time_selector      : sélecteur CSS de l'heure (dans le bloc)
#   spots_selector     : sélecteur CSS des places restantes (dans le bloc, ou None)
#   default_capacity   : nombre de places total si le site ne l'affiche pas

GYMS = [
    # ── EXEMPLE (à remplacer par tes vraies salles) ──────────────────────────
    # {
    #     "id": "crossfit_paris",
    #     "name": "CrossFit Paris",
    #     "url": "https://crossfitparis.com/planning",
    #     "session_selector": "div.session-block",
    #     "title_selector": "h3.session-title",
    #     "coach_selector": "span.coach-name",
    #     "time_selector": "span.session-time",
    #     "spots_selector": "span.spots-left",   # None si non disponible
    #     "default_capacity": 15,
    # },
]


# ── Alertes ───────────────────────────────────────────────────────────────────
ALERT_CONFIG = {
    # Envoie une alerte quand il reste ce nombre de places ou moins
    "spots_threshold": 2,
}


# ── Email ─────────────────────────────────────────────────────────────────────
# Pour utiliser Gmail :
#   1. Active la validation en 2 étapes sur ton compte Google
#   2. Va sur https://myaccount.google.com/apppasswords
#   3. Crée un "mot de passe d'application" → copie les 16 caractères ici
#
# Pour utiliser un autre fournisseur, adapte smtp_host et smtp_port

EMAIL_CONFIG = {
    "from": "ton_email@gmail.com",          # ← ton adresse Gmail
    "to": "ton_email@gmail.com",            # ← où recevoir les alertes
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "smtp_user": "ton_email@gmail.com",     # ← ton adresse Gmail
    "smtp_password": "xxxx xxxx xxxx xxxx", # ← mot de passe d'application (16 car.)
}
