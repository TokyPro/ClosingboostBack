import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.core import CopilotMessage, CopilotChatResponse, RequirementsSummary
from .ai_service import AIIntelligenceService

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

COPILOT_SYSTEM_PROMPT = """Tu es un Expert Sales Executive senior spécialisé dans la vente de solutions technologiques complexes (SaaS, Cloud, IA).
Ton objectif est d'assister un commercial pendant un rendez-vous client pour recueillir les besoins techniques tout en boostant la relation stratégique.

Directives de conversation :
1. Analyse l'historique pour identifier les besoins déjà remplis (description, plateforme, fonctionnalités, hébergement, données, utilisateurs, délai, intégrations).
2. Ne sois pas rigide : si le client donne plusieurs infos d'un coup, rebondis dessus. Si une info manque, pose une question naturelle.
3. Adopte une posture de conseiller (Consultative Selling) : ne te contente pas de poser des questions, explique POURQUOI c'est important ou suggère une bonne pratique.
4. Si tous les besoins fondamentaux sont recueillis, propose de passer à la génération du chiffrage ou du briefing stratégique.

Structure de réponse (JSON attendu) :
{
  "message": "Ta réponse textuelle au client (naturelle, empathique, professionnelle)",
  "suggestions": ["3-4 options courtes que le client pourrait répondre"],
  "requirements": {
    "description": "string ou null",
    "platform": "string ou null",
    "features": "string ou null",
    "hosting": "string ou null",
    "data_volume": "string ou null",
    "users": "string ou null",
    "timeline": "string ou null",
    "integrations": "string ou null"
  },
  "tactical_advice": "Un conseil flash destiné UNIQUEMENT au commercial (ex: 'Pose une question sur le budget pour valider la qualification' ou 'Souligne notre expertise en sécurité car le client semble inquiet')",
  "progress": 0-100 (estimation du remplissage des besoins),
  "is_complete": true/false
}

Réponds UNIQUEMENT en JSON valide, sans markdown, sans blocs de code."""

# ── Service ────────────────────────────────────────────────────────────────────

class CopilotService:
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.ai_service = AIIntelligenceService()

    async def process_chat(self, messages: List[CopilotMessage]) -> CopilotChatResponse:
        """
        AI-driven requirements gathering and sales coaching.
        """
        # Build prompt history
        history = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

        prompt = f"{COPILOT_SYSTEM_PROMPT}\n\nHistorique de la conversation :\n{json.dumps(history, ensure_ascii=False)}"

        try:
            raw_response = await self.ai_service.generate_text(prompt)
            
            # Robust JSON cleaning: extract content between first { and last }
            clean_json = raw_response.strip()
            first_brace = clean_json.find('{')
            last_brace = clean_json.rfind('}')
            
            if first_brace != -1 and last_brace != -1:
                clean_json = clean_json[first_brace:last_brace+1]
            
            data = json.loads(clean_json)
            
            # Ensure we have defaults if some keys are missing
            msg = data.get("message")
            if not msg or msg.strip() == "":
                msg = "Je continue de noter vos besoins. Qu'avez-vous d'autre à me préciser ?"

            return CopilotChatResponse(
                message=msg,
                suggestions=data.get("suggestions", []),
                requirements=RequirementsSummary(**data.get("requirements", {})),
                tactical_advice=data.get("tactical_advice"),
                progress=data.get("progress", 0),
                is_complete=data.get("is_complete", False)
            )
        except Exception as e:
            logger.error(f"Error in Copilot intelligent process: {e}")
            logger.debug(f"Raw response was: {raw_response if 'raw_response' in locals() else 'No response'}")
            # Fallback to a basic message if AI fails
            return CopilotChatResponse(
                message="Je suis prêt à vous écouter. Parlez-moi de votre projet.",
                suggestions=["Décrire le projet", "Parler technique"],
                requirements=RequirementsSummary(),
                tactical_advice="L'IA est temporairement indisponible, continuez le recueil manuellement.",
                progress=0,
                is_complete=False
            )

    async def generate_quote(self, requirements: RequirementsSummary) -> Dict[str, Any]:
        return await self.ai_service.generate_quote(
            description=requirements.description or "Non spécifié",
            platform=requirements.platform or "Non spécifié",
            features=requirements.features or "Non spécifié",
            hosting=requirements.hosting or "Non spécifié",
            data_volume=requirements.data_volume or "Non spécifié",
            users=requirements.users or "Non spécifié",
            timeline=requirements.timeline or "Non spécifié",
            integrations=requirements.integrations or "Non spécifié",
        )

    async def save_session(self, request: Any) -> Any:
        if not self.db:
            raise ValueError("Database session required for save_session")
        
        from .interaction_service import InteractionService
        from ..schemas.core import InteractionCreate
        
        import json as _json
        transcript = _json.dumps([{"role": m.role, "content": m.content} for m in request.messages])
        
        summary = f"Copilot requirements gathering session for {request.requirements.description or 'unspecified project'}"
        
        interaction_in = InteractionCreate(
            opportunity_id=request.opportunity_id,
            type=request.type,
            summary=summary,
            raw_transcript=transcript,
            requirements=request.requirements.model_dump()
        )
        
        interaction_service = InteractionService(self.db)
        return await interaction_service.create_interaction(interaction_in)
