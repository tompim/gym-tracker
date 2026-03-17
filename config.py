"""
Configuration — salles de sport et email.

COMMENT AJOUTER UNE NOUVELLE SALLE :
  Donne-moi l'URL dans Claude, je génère le bloc automatiquement.

CHAMPS DISPONIBLES PAR SALLE :
  id                   : identifiant unique (pas d'espaces, pas d'accents)
  name                 : nom affiché
  url                  : URL du planning public
  session_selector     : sélecteur CSS du bloc contenant UNE séance
  wait_for_selector    : sélecteur à attendre avant de lire la page (JS loading)
  extra_wait_ms        : millisecondes d'attente supplémentaire après chargement
  title_selector       : sélecteur CSS du nom de la séance (dans le bloc)
  coach_selector       : sélecteur CSS du nom du coach (dans le bloc)
  starts_at_selector   : sélecteur CSS de l'heure (dans le bloc)
  spots_selector       : sélecteur CSS des places restantes (dans le bloc)
  full_class           : classe CSS présente sur un bloc quand la séance est complète
  default_capacity     : capacité totale si le site ne l'affiche pas
  disabled             : True pour désactiver sans supprimer la config
  warning              : message affiché sur le dashboard pour cette salle
"""

import os

GYMS = [

    # ── Punch Studios ─────────────────────────────────────────────────────────
    # Plateforme : Application JS custom (React SPA)
    # URL        : https://punch-studios.com/reservation/#/studio/4
    # Notes      : L'app charge le planning via JS après navigation.
    #              Les sélecteurs ci-dessous sont basés sur les patterns typiques
    #              des apps de réservation React — à ajuster après le premier scrape.
    {
        "id": "punch_studios",
        "name": "Punch Studios",
        "url": "https://punch-studios.com/reservation/#/studio/4",
        "session_selector": ".class-item, .session-item, .booking-slot, [class*='class'], [class*='session']",
        "wait_for_selector": ".class-item, .session-item, .booking-slot",
        "extra_wait_ms": 3000,
        "title_selector": "[class*='title'], [class*='name'], h3, h4",
        "coach_selector": "[class*='coach'], [class*='instructor'], [class*='teacher']",
        "starts_at_selector": "[class*='time'], [class*='hour'], [class*='horaire'], time",
        "spots_selector": "[class*='spot'], [class*='place'], [class*='avail'], [class*='remain']",
        "default_capacity": 15,
    },

    # ── Sant Roch ─────────────────────────────────────────────────────────────
    # Plateforme : Mariana Tek (SaaS de réservation)
    # URL        : https://sant-roch.com/schedule
    # Notes      : Mariana Tek charge les classes dans des éléments <li> ou <div>
    #              avec des classes spécifiques à leur framework.
    #              Le planning est un iframe chargé dynamiquement.
    {
        "id": "sant_roch",
        "name": "Sant Roch",
        "url": "https://sant-roch.com/schedule",
        "session_selector": "li.class-list-item, div.class-list-item, [data-testid='class-item'], .schedule-class",
        "wait_for_selector": "li.class-list-item, .schedule-class, [data-testid='class-item']",
        "extra_wait_ms": 4000,
        "title_selector": ".class-name, .class-title, [data-testid='class-name'], h3",
        "coach_selector": ".instructor-name, .coach-name, [data-testid='instructor']",
        "starts_at_selector": ".class-time, .start-time, [data-testid='class-time'], time",
        "spots_selector": ".spots-remaining, .availability, [data-testid='spots']",
        "full_class": "is-full",
        "default_capacity": 20,
    },

    # ── Lagreeness ────────────────────────────────────────────────────────────
    # Plateforme : Mindbody Branded Web (widget ID: 4233980e908)
    # URL widget : https://brandedweb-next.mindbodyonline.com/components/widgets/schedules/view/4233980e908/schedule
    #
    # Deux studios : Paris 17 (6 machines) et Paris 3 (10 machines)
    # Le widget Mindbody affiche les deux studios — on les sépare par location_filter si besoin
    {
        "id": "lagreeness_paris17",
        "name": "Lagreeness Paris 17",
        "url": "https://brandedweb-next.mindbodyonline.com/components/widgets/schedules/view/4233980e908/schedule",
        # Mindbody Branded Web v2 — sélecteurs basés sur la structure connue du widget
        "session_selector": (
            "[class*='ClassItem'], [class*='class-item'], "
            "[class*='ScheduleItem'], [class*='schedule-item'], "
            "li[class*='class'], div[class*='ClassRow']"
        ),
        "wait_for_selector": (
            "[class*='ClassItem'], [class*='ScheduleItem'], "
            "[class*='class-item'], [class*='ClassRow']"
        ),
        "extra_wait_ms": 5000,
        "title_selector": "[class*='ClassName'], [class*='class-name'], [class*='ClassTitle'], h3, h4",
        "coach_selector": "[class*='InstructorName'], [class*='instructor'], [class*='coach'], [class*='Staff']",
        "starts_at_selector": "[class*='ClassTime'], [class*='StartTime'], [class*='time'], time",
        "spots_selector": "[class*='Spots'], [class*='spots'], [class*='Availability'], [class*='availability']",
        "full_class": "full",
        "default_capacity": 6,   # Paris 17 : 6 Megareformers
        "location_filter": "17",  # Filtre optionnel pour ne garder que Paris 17
    },
    {
        "id": "lagreeness_paris3",
        "name": "Lagreeness Paris 3",
        "url": "https://brandedweb-next.mindbodyonline.com/components/widgets/schedules/view/4233980e908/schedule",
        "session_selector": (
            "[class*='ClassItem'], [class*='class-item'], "
            "[class*='ScheduleItem'], [class*='schedule-item'], "
            "li[class*='class'], div[class*='ClassRow']"
        ),
        "wait_for_selector": (
            "[class*='ClassItem'], [class*='ScheduleItem'], "
            "[class*='class-item'], [class*='ClassRow']"
        ),
        "extra_wait_ms": 5000,
        "title_selector": "[class*='ClassName'], [class*='class-name'], [class*='ClassTitle'], h3, h4",
        "coach_selector": "[class*='InstructorName'], [class*='instructor'], [class*='coach'], [class*='Staff']",
        "starts_at_selector": "[class*='ClassTime'], [class*='StartTime'], [class*='time'], time",
        "spots_selector": "[class*='Spots'], [class*='spots'], [class*='Availability'], [class*='availability']",
        "full_class": "full",
        "default_capacity": 10,  # Paris 3 : 10 Megapro
        "location_filter": "3",   # Filtre optionnel pour ne garder que Paris 3
    },

    # ── Out Sports Club ───────────────────────────────────────────────────────
    # Plateforme : Bsport (SaaS de réservation)
    # URL        : https://www.outsportsclub.com/planning
    # Notes      : Bsport intègre son widget via une iframe ou un composant JS.
    #              Le planning est chargé depuis backoffice.bsport.io.
    #              Les sélecteurs ciblent les éléments rendus par le widget Bsport.
    {
        "id": "out_sports_club",
        "name": "Out Sports Club",
        "url": "https://www.outsportsclub.com/planning",
        "session_selector": (
            ".bsport-class, .bsport-occurrence, "
            "[class*='occurrence'], [class*='class-card'], "
            ".fc-event, .schedule-event, [class*='ClassCard']"
        ),
        "wait_for_selector": (
            ".bsport-class, .bsport-occurrence, "
            "[class*='occurrence'], .fc-event"
        ),
        "extra_wait_ms": 5000,
        "title_selector": "[class*='name'], [class*='title'], .class-name, h3, h4",
        "coach_selector": "[class*='coach'], [class*='instructor'], .coach",
        "starts_at_selector": "[class*='time'], [class*='hour'], .start-time, time",
        "spots_selector": "[class*='spot'], [class*='place'], [class*='avail']",
        "full_class": "is-full",
        "default_capacity": 20,
    },

]


# ── Alertes ───────────────────────────────────────────────────────────────────
ALERT_CONFIG = {
    "spots_threshold": 2,   # Alerte quand il reste ≤ N places
}


# ── Email ─────────────────────────────────────────────────────────────────────
# Pour Gmail :
#   1. Active la validation en 2 étapes : myaccount.google.com > Sécurité
#   2. Crée un mot de passe d'application : myaccount.google.com/apppasswords
#   3. Copie les 16 caractères générés dans smtp_password ci-dessous

EMAIL_CONFIG = {
    "from": os.environ.get("EMAIL_FROM", "ton_email@gmail.com"),
    "to": os.environ.get("EMAIL_TO", "ton_email@gmail.com"),
    "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": int(os.environ.get("SMTP_PORT", "465")),
    "smtp_user": os.environ.get("SMTP_USER", "ton_email@gmail.com"),
    "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
}
