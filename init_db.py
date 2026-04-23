import asyncio
import sys
import os

# Ajouter le dossier parent au path pour pouvoir importer 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import create_db_and_tables
from app.models import core # Import des modèles pour qu'SQLAlchemy les connaisse

async def main():
    print("Initialisation de la base de données SQLite...")
    try:
        await create_db_and_tables()
        print("Succès : La base de données 'salesboost.db' a été créée avec toutes les tables.")
    except Exception as e:
        print(f"Erreur lors de la création de la base de données : {e}")

if __name__ == "__main__":
    asyncio.run(main())
