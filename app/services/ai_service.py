import json
import logging
from typing import Dict, Any

import google.genai as genai

from ..core.config import settings

logger = logging.getLogger(__name__)
BRIEFING_PROMPT = """Tu es un Expert Sales Strategist spécialisé dans le closing de comptes B2B à haute valeur.
Génère un briefing de préparation stratégique ultra-pertinent pour l'opportunité suivante.

Détails de l'opportunité :
{context}

Objectif : Fournir au commercial une longueur d'avance psychologique et technique.

Réponds UNIQUEMENT avec un objet JSON valide (pas de markdown) avec ces champs :
{{
  "ai_strategy": "Angle d'attaque tactique : 3-4 phrases sur comment positionner l'offre face aux enjeux spécifiques détectés. Utilise un ton 'Digital Executive' (efficace, autoritaire, luxueux).",
  "ai_risk_assessment": "Analyse des risques : Identifie 2 risques critiques liés au profil client ou au projet et propose une parade.",
  "market_insights": {{
    "sector_trend": "Tendance marché : Une analyse flash du secteur de l'entreprise liée au projet.",
    "demand_index": "Indice de demande estimé (ex: +15% sur 12 mois)",
    "competitor_analysis": "Note concurrentielle : Comment se différencier sur ce deal précis."
  }},
  "buyer_persona": "Analyse du contact (si disponible) : Profil psychologique type et leviers de persuasion recommandés.",
  "value_prop_alignment": "Alignement de valeur : Comment notre solution répond précisément au problème décrit dans le titre/contexte."
}}"""


QUOTE_PROMPT = """Tu es un expert en chiffrage de projets logiciels.
Sur la base des besoins client suivants, génère un devis détaillé et réaliste.

Besoins client :
- Description : {description}
- Plateforme : {platform}
- Fonctionnalités : {features}
- Hébergement : {hosting}
- Volume de données : {data_volume}
- Utilisateurs simultanés : {users}
- Délai souhaité : {timeline}
- Intégrations : {integrations}

Génère UNIQUEMENT un objet JSON valide (sans markdown, sans blocs de code) :
{{
  "project_title": "Titre court dérivé de la description",
  "daily_rate": 650,
  "total_cost": 97500,
  "total_duration_days": 150,
  "phases": [
    {{"name": "Analyse & Conception", "duration_days": 15, "cost": 9750, "description": "Cadrage, architecture, maquettes UX"}},
    {{"name": "Développement Back-end", "duration_days": 50, "cost": 32500, "description": "API, base de données, logique métier"}},
    {{"name": "Développement Front-end", "duration_days": 45, "cost": 29250, "description": "Interfaces, intégration API"}},
    {{"name": "Intégrations & Tests", "duration_days": 25, "cost": 16250, "description": "Intégrations tierces, recette"}},
    {{"name": "Déploiement & Formation", "duration_days": 15, "cost": 9750, "description": "Mise en prod, documentation, formation"}}
  ],
  "assumptions": [
      "Taux journalier de 650 €/j HT",
      "Équipe de 2 développeurs + 1 chef de projet",
      "Hébergement non inclus"
  ]
  }}

Adapte les volumes selon la complexité (multi-plateforme +30%, intégrations multiples +20%, > 1M utilisateurs +25%)."""


COLD_AGENT_PROMPT = """Tu es l'Agent "Éclaireur" — spécialiste de la création de notoriété et de la curiosité.

Contexte du lead :
{lead_context}

Actualités récentes de l'entreprise :
{company_news}

Génère un email ultra-personnalisé basé sur une actualité récente de l'entreprise.
Objectif : créer de la curiosité et de la notoriété, PAS vendre.
Ton : professionnel, chaleureux, pertinent.

Réponds UNIQUEMENT avec un JSON valide :
{{
  "subject": "Objet de l'email (court, accrocheur, personnalisé)",
  "message": "Corps de l'email (5-7 lignes max, personnalisé sur l'actualité, avec lien CTA vers ressource à haute valeur)",
  "rationale": "Pourquoi cette approche pour ce lead (1-2 phrases)"
}}"""

WARM_AGENT_PROMPT = """Tu es l'Agent "Conseiller" — spécialiste de la création de considération et de validation du besoin.

Contexte du lead :
{lead_context}

Interactions précédentes :
{previous_interactions}

Génère un message LinkedIn personnalisé OU une invitation webinar ciblant un pain point spécifique.
Objectif : valider le besoin et créer de la considération.
Ton : consultif, empathique, expert.

Réponds UNIQUEMENT avec un JSON valide :
{{
  "channel": "linkedin ou email",
  "subject": "Objet (si email) ou null (si LinkedIn)",
  "message": "Message personnalisé (8-10 lignes, mentionne le pain point spécifique, inclut invitation webinar ou call découverte)",
  "rationale": "Pourquoi ce pain point pour ce lead (1-2 phrases)"
}}"""

HOT_AGENT_PROMPT = """Tu es l'Agent "Closer" — spécialiste de la conversion et de la prise de rendez-vous.

Contexte du lead :
{lead_context}

Score actuel : {score}/100 — LEAD CHAUD

Génère un pitch de vente direct et une proposition de créneau.
Objectif : déclencher la prise de rendez-vous IMMÉDIATEMENT.
Ton : direct, assertif, urgence maîtrisée.

Réponds UNIQUEMENT avec un JSON valide :
{{
  "subject": "Objet percutant avec proposition de valeur claire",
  "message": "Pitch direct (10-12 lignes : problème → solution → bénéfices → CTA Calendly clair)",
  "slack_notification": "Message Slack court pour le commercial (1-2 lignes, urgence, contexte lead)",
  "rationale": "Pourquoi ce lead est prêt à convertir maintenant (1-2 phrases)"
}}"""


class AIIntelligenceService:
    def __init__(self) -> None:
        self.api_key = settings.GOOGLE_API_KEY
        self.model_name = settings.GEMINI_MODEL

    def _fallback_briefing(self) -> Dict[str, Any]:
        return {
            "ai_strategy": "Angle tactique par défaut : Focus sur le ROI et la rapidité de mise en place.",
            "ai_risk_assessment": "Risque standard identifié. Préciser le planning rapidement.",
            "market_insights": {
                "sector_trend": "Demande croissante sur ce secteur.",
                "demand_index": "+10% YoY",
                "competitor_analysis": "Differentiate on service quality.",
            },
            "buyer_persona": "Profil décisionnaire classique. Focus sur les indicateurs de performance.",
            "value_prop_alignment": "Solution agile alignée sur les besoins exprimés."
        }

    async def generate_briefing(self, context: str) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("GOOGLE_API_KEY not set — returning fallback briefing.")
            return self._fallback_briefing()

        client = genai.Client(api_key=self.api_key)
        prompt = BRIEFING_PROMPT.format(context=context)

        try:
            response = await client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            text = response.text.strip()
            first_brace = text.find('{')
            last_brace = text.rfind('}')
            if first_brace != -1 and last_brace != -1:
                text = text[first_brace:last_brace+1]
            return json.loads(text)
        except Exception as exc:
            logger.error("Gemini briefing generation failed: %s", exc)
            return self._fallback_briefing()

    async def generate_quote(
        self,
        description: str = "Non spécifié",
        platform: str = "Non spécifié",
        features: str = "Non spécifié",
        hosting: str = "Non spécifié",
        data_volume: str = "Non spécifié",
        users: str = "Non spécifié",
        timeline: str = "Non spécifié",
        integrations: str = "Non spécifié",
    ) -> Dict[str, Any]:
        if not self.api_key:
            return self._demo_quote(description)

        client = genai.Client(api_key=self.api_key)
        prompt = QUOTE_PROMPT.format(
            description=description, platform=platform, features=features,
            hosting=hosting, data_volume=data_volume, users=users,
            timeline=timeline, integrations=integrations,
        )
        try:
            response = await client.aio.models.generate_content(model=self.model_name, contents=prompt)
            text = response.text.strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
            return json.loads(text)
        except Exception as exc:
            logger.error("Gemini quote generation failed: %s", exc)
            return self._demo_quote(description)

    def _demo_quote(self, description: str) -> Dict[str, Any]:
        return {
            "project_title": (description[:60] + "…") if len(description) > 60 else description or "Projet sur mesure",
            "daily_rate": 650.0,
            "total_cost": 97500.0,
            "total_duration_days": 150,
            "phases": [
                {"name": "Analyse & Conception", "duration_days": 15, "cost": 9750.0, "description": "Cadrage, architecture technique, maquettes UX/UI"},
                {"name": "Développement Back-end", "duration_days": 50, "cost": 32500.0, "description": "API REST, base de données, logique métier"},
                {"name": "Développement Front-end", "duration_days": 45, "cost": 29250.0, "description": "Interfaces utilisateur, intégration API"},
                {"name": "Intégrations & Tests", "duration_days": 25, "cost": 16250.0, "description": "Intégrations tierces, recette fonctionnelle"},
                {"name": "Déploiement & Formation", "duration_days": 15, "cost": 9750.0, "description": "Mise en production, documentation, formation"},
            ],
            "assumptions": [
                "Taux journalier de 650 €/j HT",
                "Équipe de 2 développeurs + 1 chef de projet",
                "Hébergement cloud non inclus dans ce devis",
                "Chiffrage indicatif — devis précis après réunion de cadrage",
            ],
        }

    async def generate_text(self, prompt: str) -> str:
        if not self.api_key:
            return "{}"
        client = genai.Client(api_key=self.api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model_name, contents=prompt,
            )
            return response.text.strip()
        except Exception as exc:
            logger.error("Gemini generate_text failed: %s", exc)
            return "{}"

    async def generate_cold_message(self, lead_context: str, company_news: str) -> dict:
        if not self.api_key:
            return {
                "subject": "Découvrez nos insights sectoriels exclusifs",
                "message": "Message personnalisé généré en mode démo.",
                "rationale": "Mode démo activé.",
            }
        client = genai.Client(api_key=self.api_key)
        prompt = COLD_AGENT_PROMPT.format(
            lead_context=lead_context,
            company_news=company_news or "Aucune actualité disponible",
        )
        try:
            response = await client.aio.models.generate_content(
                model=self.model_name, contents=prompt
            )
            text = response.text.strip()
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1:
                text = text[first_brace : last_brace + 1]
            return json.loads(text)
        except Exception as exc:
            logger.error("Cold agent generation failed: %s", exc)
            return {
                "subject": "Nos insights pour votre secteur",
                "message": "Message de prospection personnalisé.",
                "rationale": "Fallback activé.",
            }

    async def generate_warm_message(
        self, lead_context: str, previous_interactions: str
    ) -> dict:
        if not self.api_key:
            return {
                "channel": "email",
                "subject": "Invitation : Webinar sur vos enjeux métier",
                "message": "Message de nurturing personnalisé.",
                "rationale": "Mode démo.",
            }
        client = genai.Client(api_key=self.api_key)
        prompt = WARM_AGENT_PROMPT.format(
            lead_context=lead_context,
            previous_interactions=previous_interactions or "Aucune interaction précédente",
        )
        try:
            response = await client.aio.models.generate_content(
                model=self.model_name, contents=prompt
            )
            text = response.text.strip()
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1:
                text = text[first_brace : last_brace + 1]
            return json.loads(text)
        except Exception as exc:
            logger.error("Warm agent generation failed: %s", exc)
            return {
                "channel": "linkedin",
                "subject": None,
                "message": "Message de consideration personnalisé.",
                "rationale": "Fallback activé.",
            }

    async def generate_hot_message(self, lead_context: str, score: float) -> dict:
        if not self.api_key:
            return {
                "subject": "Proposition : 15min pour transformer votre pipeline",
                "message": "Pitch de conversion personnalisé. Lien Calendly : https://calendly.com/salesboost",
                "slack_notification": "Lead chaud prêt à convertir — appelez dans 5 minutes!",
                "rationale": "Mode démo.",
            }
        client = genai.Client(api_key=self.api_key)
        prompt = HOT_AGENT_PROMPT.format(lead_context=lead_context, score=score)
        try:
            response = await client.aio.models.generate_content(
                model=self.model_name, contents=prompt
            )
            text = response.text.strip()
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1:
                text = text[first_brace : last_brace + 1]
            return json.loads(text)
        except Exception as exc:
            logger.error("Hot agent generation failed: %s", exc)
            return {
                "subject": "Prêt pour une démo de 15 minutes ?",
                "message": "Pitch direct de conversion.",
                "slack_notification": "Lead chaud — action requise!",
                "rationale": "Fallback activé.",
            }

    async def analyze_transcript(self, transcript: str) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured in the environment.")

        client = genai.Client(api_key=self.api_key)
        prompt = f"""Analyze this sales call transcript and extract key insights.
Transcript: {transcript}

Respond ONLY with valid JSON:
{{
  "keywords": ["list", "of", "key", "terms"],
  "suggestions": [
    {{"title": "suggestion title", "description": "brief description", "impact": "High|Medium|Low"}}
  ]
}}"""

        response = await client.aio.models.generate_content(model=self.model_name, contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text
        return json.loads(text)
