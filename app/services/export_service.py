from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.core import Lead
from ..repositories.lead_repository import LeadRepository

logger = logging.getLogger(__name__)

AIRTABLE_API_URL = "https://api.airtable.com/v0"
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
AIRTABLE_BATCH = 10


def _airtable_fields(lead: Lead) -> dict:
    raw = {
        "Nom": lead.contact_name,
        "Entreprise": lead.company_name,
        "Poste": lead.contact_title,
        "Email": lead.contact_email,
        "Téléphone": lead.contact_phone,
        "LinkedIn": lead.linkedin_url,
        "Site Web": lead.website_url,
        "Localisation": lead.location,
        "Secteur": lead.activity_sector,
        "Score": lead.score,
        "Palier": lead.tier,
        "Statut": lead.status,
        "Notes": lead.notes,
        "Résumé": lead.summary,
        "Source": lead.source,
    }
    return {k: v for k, v in raw.items() if v is not None}


def _notion_properties(lead: Lead) -> dict:
    title = lead.contact_name or lead.company_name or "Lead"
    props: dict = {"Nom": {"title": [{"text": {"content": title}}]}}

    def rich(v: str) -> dict:
        return {"rich_text": [{"text": {"content": v[:2000]}}]}

    if lead.company_name:
        props["Entreprise"] = rich(lead.company_name)
    if lead.contact_title:
        props["Poste"] = rich(lead.contact_title)
    if lead.contact_email:
        props["Email"] = {"email": lead.contact_email}
    if lead.contact_phone:
        props["Téléphone"] = {"phone_number": lead.contact_phone}
    if lead.linkedin_url:
        props["LinkedIn"] = {"url": lead.linkedin_url}
    if lead.website_url:
        props["Site Web"] = {"url": lead.website_url}
    if lead.location:
        props["Localisation"] = rich(lead.location)
    if lead.activity_sector:
        props["Secteur"] = rich(lead.activity_sector)
    if lead.score is not None:
        props["Score"] = {"number": lead.score}
    if lead.tier:
        props["Palier"] = {"select": {"name": lead.tier}}
    if lead.status:
        props["Statut"] = {"select": {"name": lead.status}}
    if lead.summary:
        props["Résumé"] = rich(lead.summary)
    if lead.source:
        props["Source"] = {"select": {"name": lead.source}}
    return props


class ExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = LeadRepository(db)

    async def _fetch_leads(self, lead_ids: list[str]) -> list[Lead]:
        leads: list[Lead] = []
        for lid in lead_ids:
            lead = await self.repo.get_by_id(lid)
            if lead:
                leads.append(lead)
        return leads

    async def export_to_airtable(
        self,
        lead_ids: list[str],
        api_key: str,
        base_id: str,
        table_name: str,
    ) -> dict:
        leads = await self._fetch_leads(lead_ids)
        if not leads:
            return {"exported": 0, "errors": []}

        exported = 0
        errors: list[str] = []
        url = f"{AIRTABLE_API_URL}/{base_id}/{table_name}"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            for lead in leads:
                payload = {"fields": _airtable_fields(lead)}
                try:
                    if lead.airtable_id:
                        # Update existing record
                        resp = await client.patch(f"{url}/{lead.airtable_id}", json=payload, headers=headers)
                    else:
                        # Create new record
                        resp = await client.post(url, json={"records": [payload]}, headers=headers)
                    
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        # If it was a create, we get back a list of records
                        if not lead.airtable_id and "records" in data:
                            lead.airtable_id = data["records"][0]["id"]
                        elif lead.airtable_id:
                             # It was a patch, we get back the record directly
                             pass
                        
                        await self.repo.update(lead)
                        exported += 1
                    else:
                        errors.append(f"Lead {lead.id}: HTTP {resp.status_code} — {resp.text[:300]}")
                except Exception as exc:
                    errors.append(f"Lead {lead.id}: {exc}")

        return {"exported": exported, "errors": errors}

    async def export_to_notion(
        self,
        lead_ids: list[str],
        token: str,
        database_id: str,
    ) -> dict:
        leads = await self._fetch_leads(lead_ids)
        if not leads:
            return {"exported": 0, "errors": []}

        exported = 0
        errors: list[str] = []
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for lead in leads:
                payload = {"properties": _notion_properties(lead)}
                try:
                    if lead.notion_id:
                        # Update existing page
                        resp = await client.patch(f"{NOTION_API_URL}/pages/{lead.notion_id}", json=payload, headers=headers)
                    else:
                        # Create new page
                        payload["parent"] = {"database_id": database_id}
                        resp = await client.post(f"{NOTION_API_URL}/pages", json=payload, headers=headers)
                    
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        if not lead.notion_id:
                            lead.notion_id = data["id"]
                        await self.repo.update(lead)
                        exported += 1
                    else:
                        errors.append(f"Lead {lead.id}: HTTP {resp.status_code} — {resp.text[:300]}")
                except Exception as exc:
                    errors.append(f"Lead {lead.id}: {exc}")

        return {"exported": exported, "errors": errors}

    async def import_from_airtable(
        self,
        api_key: str,
        base_id: str,
        table_name: str,
    ) -> dict:
        url = f"{AIRTABLE_API_URL}/{base_id}/{table_name}"
        headers = {"Authorization": f"Bearer {api_key}"}
        imported = 0
        errors = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return {"imported": 0, "errors": [f"HTTP {resp.status_code}: {resp.text[:300]}"]}
                
                records = resp.json().get("records", [])
                for rec in records:
                    air_id = rec["id"]
                    fields = rec["fields"]
                    
                    # Check if already exists
                    lead = await self.repo.get_by_airtable_id(air_id)
                    if not lead:
                        # Create new lead from Airtable fields
                        lead = Lead(
                            airtable_id=air_id,
                            contact_name=fields.get("Nom"),
                            company_name=fields.get("Entreprise"),
                            contact_title=fields.get("Poste"),
                            contact_email=fields.get("Email"),
                            contact_phone=fields.get("Téléphone"),
                            linkedin_url=fields.get("LinkedIn"),
                            website_url=fields.get("Site Web"),
                            location=fields.get("Localisation"),
                            activity_sector=fields.get("Secteur"),
                            score=fields.get("Score", 0.0),
                            tier=fields.get("Palier", "cold"),
                            status=fields.get("Statut", "new"),
                            notes=fields.get("Notes"),
                            summary=fields.get("Résumé"),
                            source=fields.get("Source", "web"),
                        )
                        await self.repo.create(lead)
                        imported += 1
                    else:
                        # Update existing lead from Airtable (bidirectional)
                        lead.contact_name = fields.get("Nom", lead.contact_name)
                        lead.company_name = fields.get("Entreprise", lead.company_name)
                        lead.contact_email = fields.get("Email", lead.contact_email)
                        await self.repo.update(lead)
                        imported += 1
                        
            return {"imported": imported, "errors": errors}
        except Exception as exc:
            return {"imported": 0, "errors": [str(exc)]}

    async def import_from_notion(
        self,
        token: str,
        database_id: str,
    ) -> dict:
        url = f"{NOTION_API_URL}/databases/{database_id}/query"
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        imported = 0
        errors = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers)
                if resp.status_code != 200:
                    return {"imported": 0, "errors": [f"HTTP {resp.status_code}: {resp.text[:300]}"]}
                
                results = resp.json().get("results", [])
                for page in results:
                    notion_id = page["id"]
                    props = page["properties"]
                    
                    def get_val(p_name: str, p_type: str = "rich_text"):
                        p = props.get(p_name, {})
                        if p_type == "title":
                            return p.get("title", [{}])[0].get("plain_text")
                        if p_type == "rich_text":
                            return p.get("rich_text", [{}])[0].get("plain_text")
                        if p_type == "email":
                            return p.get("email")
                        if p_type == "phone_number":
                            return p.get("phone_number")
                        if p_type == "url":
                            return p.get("url")
                        if p_type == "number":
                            return p.get("number")
                        if p_type == "select":
                            return p.get("select", {}).get("name")
                        return None

                    lead = await self.repo.get_by_notion_id(notion_id)
                    if not lead:
                        lead = Lead(
                            notion_id=notion_id,
                            contact_name=get_val("Nom", "title"),
                            company_name=get_val("Entreprise"),
                            contact_title=get_val("Poste"),
                            contact_email=get_val("Email", "email"),
                            contact_phone=get_val("Téléphone", "phone_number"),
                            linkedin_url=get_val("LinkedIn", "url"),
                            website_url=get_val("Site Web", "url"),
                            location=get_val("Localisation"),
                            activity_sector=get_val("Secteur"),
                            score=get_val("Score", "number") or 0.0,
                            tier=get_val("Palier", "select") or "cold",
                            status=get_val("Statut", "select") or "new",
                            summary=get_val("Résumé"),
                            source=get_val("Source", "select") or "web",
                        )
                        await self.repo.create(lead)
                        imported += 1
                    else:
                        # Update existing
                        lead.contact_name = get_val("Nom", "title") or lead.contact_name
                        lead.company_name = get_val("Entreprise") or lead.company_name
                        await self.repo.update(lead)
                        imported += 1
                        
            return {"imported": imported, "errors": errors}
        except Exception as exc:
            return {"imported": 0, "errors": [str(exc)]}
