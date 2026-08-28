import json
from pymongo import MongoClient
from pathlib import Path

mongoClient: MongoClient = MongoClient("mongodb://localhost:27017")
db = mongoClient['TCC']
collection = db['Docentes']

ROOT_DIR = Path(__file__).resolve().parent
caminho_json = ROOT_DIR / "data" / "silver" / "professores_unificados.json"

with open(caminho_json, encoding="utf-8") as f:
    file_data = json.load(f)

collection.insert_many(file_data)