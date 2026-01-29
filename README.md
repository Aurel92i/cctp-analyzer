# 🏛️ CCTP Analyzer

**Application d'analyse automatisée de CCTP pour les marchés publics**

Développé pour **Chardonnet Conseil** - Expert Marchés Publics

---

## 🎯 Fonctionnalités

- **Upload double** : CCAG (référentiel) + CCTP (à analyser)
- **Analyse intelligente** : GPT-4 via OpenRouter
- **3 sources croisées** : CCAG + CCTP + Code de la Commande Publique
- **Export professionnel** : Document Word avec commentaires de révision natifs

---

## 🚀 Installation rapide

### Option 1 : Docker (recommandé)

```bash
# Copier la configuration
cp .env.example .env
nano .env  # Ajouter votre clé OpenRouter

# Lancer
docker-compose up -d
```

### Option 2 : Installation directe

```bash
# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer
cp .env.example .env
nano .env  # Ajouter votre clé OpenRouter

# Lancer
python app.py
```

---

## 🔧 Configuration

| Variable | Description | Obligatoire |
|----------|-------------|-------------|
| `OPENROUTER_API_KEY` | Clé API OpenRouter | ✅ |
| `OPENROUTER_MODEL` | Modèle LLM (défaut: gpt-4-turbo) | ❌ |
| `SECRET_KEY` | Clé secrète Flask | ✅ en prod |

---

## 📁 Structure

```
cctp-analyzer/
├── app.py                  # Application Flask
├── config.py               # Configuration
├── services/
│   ├── document_extractor.py
│   ├── gpt_analyzer.py
│   └── word_annotator.py
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   └── js/app.js
├── data/
│   └── code_commande_publique.txt  # Fixe
├── uploads/
│   ├── ccag/
│   └── cctp/
└── outputs/
```

---

## 📖 Utilisation

1. Accéder à `http://localhost:5001`
2. Uploader un **CCAG** (selon le domaine)
3. Uploader un **CCTP** (à analyser)
4. Cliquer sur **Analyser**
5. Télécharger le **CCTP annoté**

---

## 📄 Domaines CCAG supportés

- Travaux
- Fournitures courantes et services
- Prestations intellectuelles (PI)
- Techniques de l'information (TIC)
- Maîtrise d'œuvre (MOE)
- Marchés industriels

---

## 🔒 Sécurité

- Les fichiers uploadés sont supprimés après traitement
- Les clés API ne sont jamais exposées côté client
- HTTPS recommandé en production

---

## 📞 Support

**Chardonnet Conseil**  
Expert en Marchés Publics

---

*Version 1.0.0 - Janvier 2026*
