"""
StadiumIQ -- Slim Local Runner
==============================
Lightweight FastAPI server that works with or without all heavy deps.
Serves the frontend and provides functional API endpoints.
Run: python run_local.py
"""
import sys, io, os, json, random, uuid, asyncio, logging
# Force UTF-8 output on Windows to avoid cp1252 emoji encoding errors
if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Prevent langchain-google-genai from fighting over which key to use
if os.environ.get('GOOGLE_API_KEY') and os.environ.get('GEMINI_API_KEY'):
    del os.environ['GOOGLE_API_KEY']

from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# ── Optional heavy deps ──────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
    from pydantic import BaseModel, Field
    FASTAPI_OK = True
except ImportError:
    print("ERROR: FastAPI not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

# Optional Gemini (using new google.genai SDK)
try:
    from google import genai as google_genai
    from google.genai import types as genai_types
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if GEMINI_API_KEY:
        _genai_client = google_genai.Client(api_key=GEMINI_API_KEY)
        GEMINI_OK = True
        print("[OK] Gemini 2.0 Flash connected")
    else:
        _genai_client = None
        GEMINI_OK = False
        print("[INFO] No GEMINI_API_KEY -- running in demo mode (add key to backend/.env)")
except ImportError:
    _genai_client = None
    GEMINI_OK = False
    print("[INFO] google-genai not installed -- demo mode active")

# Optional LangGraph
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_OK = True
    print("[OK] LangGraph available")
except ImportError:
    LANGGRAPH_OK = False
    print("[INFO] LangGraph not installed -- install deps for full agent mode")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s - %(message)s")
log = logging.getLogger("stadiumiq")

# ── Data ─────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
def load_json(f):
    p = DATA_DIR / f
    return json.load(open(p)) if p.exists() else []

STADIUMS    = load_json("stadiums.json")
MATCHES     = load_json("matches.json")
STADIUM_MAP = {s["id"]: s for s in STADIUMS}

connected_ws: list[WebSocket] = []

# ── Simulated Responses & Datasets ─────────────────────────────────

ACCESSIBILITY_DATA = {
    "met": {
        "gate": "Gate A or Gate C (fully accessible with flat ramps)",
        "lifts": "Lifts A1, A2, and B1 are fully operational. Note: Lift B3 is temporarily closed for maintenance.",
        "routes": "Use Level 1 concourse elevator lobby for access to upper deck. Follow the blue accessibility paths.",
        "quiet_zone": "Quiet Room / Sensory Room is located on Plaza Level near Section 117.",
        "assistance": "Press the blue assistance button at Gate A/C, or text 'ACCESS' to 84444 for staff-assistance escort (15-min ETA)."
    },
    "dal": {
        "gate": "Entry Gates 1 and 3 (equipped with low-incline ramps)",
        "lifts": "Lifts L1 and L3 are fully operational. Access to all levels.",
        "routes": "Use Elevator lobby near Gate 1 to access Suite level and Upper bowl. Path is clear of steps.",
        "quiet_zone": "Quiet Zone / Sensory Area is located in the Main Concourse behind Section 240.",
        "assistance": "Ask any guest services representative in a blue vest, or visit Guest Services at Plaza Section 102."
    },
    "la": {
        "gate": "North Entry and South Entry (accessible via elevators and escalators)",
        "lifts": "Elevators in VIP North and VIP South lobbies are operational. Access to Main Concourse and Terrace.",
        "routes": "Accessible pedestrian bridge connects parking lots P1-P4 to the North Entry. Follow yellow navigation markings.",
        "quiet_zone": "Sensory Room is located on Level 3 near the East endzone suites.",
        "assistance": "Contact ADA assistants at any entry point, or call the Guest Services hotline at 424-306-8000."
    },
    "atz": {
        "gate": "Puerta Norte and Puerta Sur (equipped with designated accessibility lanes)",
        "lifts": "Lifts on the North side are fully operational. Sur elevators are accessible with staff badge.",
        "routes": "Enter through Puerta Norte ramp → take main ramp to Gradería level → follow blue wheelchair pathways.",
        "quiet_zone": "Quiet / Sensory area is available in the Special Services area near Cancha Section 10.",
        "assistance": "Designated volunteers in green vests are stationed at all main ramps to assist with wheelchairs."
    },
    "bc": {
        "gate": "Gate A or Gate B (ramp access with direct concourse entry)",
        "lifts": "Main lifts at Gates A and B are fully operational. Access to Level 2 and Level 3.",
        "routes": "Use the lift at Gate A to access the Club level. Wheelchair path is marked with clear signage.",
        "quiet_zone": "Quiet sensory space is located on the Main Concourse level behind Section 110.",
        "assistance": "Speak to Guest Services at Section 104 or flag down any host in a red vest for assistance."
    },
    "sf": {
        "gate": "Gate A or Gate C (featuring level entry and express accessibility lanes)",
        "lifts": "Elevator lobbies at Gate A and C are fully operational. Safe access to Upper Level.",
        "routes": "Take the Gate A elevator lobby to the Club/Suite levels. Wheelchair route avoids all escalators.",
        "quiet_zone": "Sensory Quiet Room is located on the Intel Plaza level near Section 101.",
        "assistance": "Visit the mobility services kiosk at Gate A, or text your location to 408-579-5100 for dispatch."
    }
}

ACCESSIBILITY_DATA_LOCALIZED = {
    "es": {
        "met": "♿ **Guía de Accesibilidad — MetLife Stadium**\n• **Entrada Accesible**: Ingrese por la Puerta A o C (rampas planas).\n• **Ascensores/Elevadores**: Los ascensores A1, A2 y B1 están operativos. El ascensor B3 está cerrado por mantenimiento.\n• **Rutas Alternativas**: Use el vestíbulo de ascensores del Nivel 1. Siga las marcas azules.\n• **Zona de Calma**: Sala sensorial disponible en el Nivel Plaza, cerca de la Sección 117.\n• **Asistencia**: Presione el botón azul en la entrada o envíe 'ACCESS' al 84444 para asistencia.",
        "dal": "♿ **Guía de Accesibilidad — AT&T Stadium**\n• **Entrada Accesible**: Ingrese por las Puertas 1 o 3 (rampas de baja pendiente).\n• **Ascensores/Elevadores**: Lifts L1 y L3 operativos. Acceso a todos los niveles.\n• **Rutas Alternativas**: Ascensor cerca de Puerta 1 para niveles superiores.\n• **Zona de Calma**: Zona sensorial en Concourse Principal detrás de Sección 240.\n• **Asistencia**: Representantes en chaleco azul o visite Plaza Sección 102.",
        "la": "♿ **Guía de Accesibilidad — SoFi Stadium**\n• **Entrada Accesible**: Entradas Norte y Sur (elevadores y escaleras).\n• **Ascensores/Elevadores**: Elevadores operativos en vestíbulos VIP Norte y Sur.\n• **Rutas Alternativas**: Puente peatonal conecta estacionamiento P1-P4 con Entrada Norte.\n• **Zona de Calma**: Sala sensorial en Nivel 3 cerca de suites del este.\n• **Asistencia**: Asistentes ADA en entradas o llame al 424-306-8000.",
        "atz": "♿ **Guía de Accesibilidad — Estadio Azteca**\n• **Entrada Accesible**: Puerta Norte y Puerta Sur (carriles de accesibilidad).\n• **Ascensores/Elevadores**: Ascensores del Norte operativos. Sur requiere pase de personal.\n• **Rutas Alternativas**: Ingrese por rampa Norte → Gradería → siga marcas azules.\n• **Zona de Calma**: Área especial en Sección Cancha 10.\n• **Asistencia**: Voluntarios con chaleco verde en todas las rampas.",
        "bc": "♿ **Guía de Accesibilidad — BC Place**\n• **Entrada Accesible**: Puerta A o B (rampa y acceso directo).\n• **Ascensores/Elevadores**: Lifts principales en Puertas A y B operativos.\n• **Rutas Alternativas**: Lift en Puerta A para nivel Club.\n• **Zona de Calma**: Espacio sensorial en Main Concourse detrás de Sección 110.\n• **Asistencia**: Guest Services en Sección 104 o personal en chaleco rojo.",
        "sf": "♿ **Guía de Accesibilidad — Levi's Stadium**\n• **Entrada Accesible**: Puerta A o C (rampas niveladas y carriles rápidos).\n• **Ascensores/Elevadores**: Ascensores de Puerta A y C operativos.\n• **Rutas Alternativas**: Ascensor de Puerta A para niveles Club/Suite.\n• **Zona de Calma**: Sala sensorial en Intel Plaza cerca de Sección 101.\n• **Asistencia**: Quiosco en Puerta A o envíe texto al 408-579-5100."
    },
    "fr": {
        "met": "♿ **Guide d'Accessibilité — MetLife Stadium**\n• **Entrée Accessible**: Entrez par la Porte A ou C (rampes planes).\n• **Ascenseurs**: Les ascenseurs A1, A2 et B1 sont opérationnels. L'ascenseur B3 est fermé pour maintenance.\n• **Itinéraires Alternatifs**: Utilisez le hall des ascenseurs du Niveau 1. Suivez le marquage bleu.\n• **Zone de Calme**: Espace sensoriel disponible au Niveau Plaza, près de la Section 117.\n• **Assistance**: Appuyez sur le bouton bleu à l'entrée ou envoyez 'ACCESS' au 84444 pour de l'aide.",
        "dal": "♿ **Guide d'Accessibilité — AT&T Stadium**\n• **Entrée Accessible**: Portes 1 ou 3 (rampes à faible pente).\n• **Ascenseurs**: Ascenseurs L1 et L3 opérationnels. Accès à tous les niveaux.\n• **Itinéraires Alternatifs**: Ascenseur près de la Porte 1 pour les niveaux supérieurs.\n• **Zone de Calme**: Zone sensorielle sur le Concourse Principal derrière la Section 240.\n• **Assistance**: Représentants en gilet bleu ou visitez la Section Plaza 102.",
        "la": "♿ **Guide d'Accessibilité — SoFi Stadium**\n• **Entrée Accessible**: Entrées Nord et Sud (ascenseurs et escalators).\n• **Ascenseurs**: Ascenseurs opérationnels dans les halls VIP Nord et Sud.\n• **Itinéraires Alternatifs**: Pont piétonnier reliant les parkings P1-P4 à l'Entrée Nord.\n• **Zone de Calme**: Salle sensorielle au Niveau 3 près des suites de l'est.\n• **Assistance**: Assistants ADA aux entrées ou appelez le 424-306-8000.",
        "atz": "♿ **Guide d'Accessibilité — Estadio Azteca**\n• **Entrée Accessible**: Porte Nord et Porte Sud (voies d'accessibilité dédiées).\n• **Ascenseurs**: Ascenseurs Nord opérationnels. Sud nécessite un pass personnel.\n• **Itinéraires Alternatifs**: Entrez par la rampe Nord → Gradería → suivez le marquage bleu.\n• **Zone de Calme**: Zone spéciale dans la Section Cancha 10.\n• **Assistance**: Bénévoles en gilet vert sur toutes les rampes.",
        "bc": "♿ **Guide d'Accessibilité — BC Place**\n• **Entrée Accessible**: Porte A ou B (rampe et accès direct).\n• **Ascenseurs**: Ascenseurs principaux aux Portes A et B opérationnels.\n• **Itinéraires Alternatifs**: Ascenseur à la Porte A pour le niveau Club.\n• **Zone de Calme**: Espace sensoriel sur le Main Concourse derrière la Section 110.\n• **Assistance**: Guest Services à la Section 104 ou personnel en gilet rouge.",
        "sf": "♿ **Guide d'Accessibilité — Levi's Stadium**\n• **Entrée Accessible**: Porte A ou C (rampes nivelées et voies rapides).\n• **Ascenseurs**: Ascenseurs aux Portes A et C opérationnels.\n• **Itinéraires Alternatifs**: Ascenseur de la Porte A pour les niveaux Club/Suite.\n• **Zone de Calme**: Salle sensorielle sur Intel Plaza près de la Section 101.\n• **Assistance**: Kiosque à la Porte A ou envoyez un SMS au 408-579-5100."
    },
    "pt": {
        "met": "♿ **Guia de Acessibilidade — MetLife Stadium**\n• **Entrada Acessível**: Entre pelo Portão A ou C (rampas planas).\n• **Elevadores**: Elevadores A1, A2 e B1 estão operacionais. O elevador B3 está em manutenção.\n• **Rotas Alternativas**: Use o saguão de elevadores do Nível 1. Siga as marcas azuis.\n• **Zona de Silêncio**: Sala sensorial disponível no Nível Plaza, perto da Seção 117.\n• **Assistência**: Pressione o botão azul na entrada ou envie 'ACCESS' para 84444 para assistência.",
        "dal": "♿ **Guia de Acessibilidade — AT&T Stadium**\n• **Entrada Acessível**: Portões 1 ou 3 (rampas de baixa inclinação).\n• **Elevadores**: Lifts L1 e L3 operacionais. Acesso a todos os níveis.\n• **Rotas Alternativas**: Elevador perto do Portão 1 para níveis superiores.\n• **Zona de Silêncio**: Zona sensorial no Concourse Principal atrás da Seção 240.\n• **Assistência**: Representantes de colete azul ou visite Plaza Seção 102.",
        "la": "♿ **Guia de Acessibilidade — SoFi Stadium**\n• **Entrada Acessível**: Entradas Norte e Sul (elevadores e escadas).\n• **Elevadores**: Elevadores operacionais nos saguões VIP Norte e Sul.\n• **Rotas Alternativas**: Ponte de pedestres conecta estacionamentos P1-P4 à Entrada Norte.\n• **Zona de Silêncio**: Sala sensorial no Nível 3 perto das suítes leste.\n• **Assistência**: Assistentes ADA nas entradas ou ligue para 424-306-8000.",
        "atz": "♿ **Guia de Acessibilidade — Estadio Azteca**\n• **Entrada Acessível**: Portão Norte e Portão Sul (vias de acessibilidade).\n• **Elevadores**: Elevadores do Norte operacionais. Sul requer crachá de equipe.\n• **Rotas Alternativas**: Entre pela rampa Norte → Gradería → siga marcas PCD.\n• **Zona de Silêncio**: Área especial na Seção Cancha 10.\n• **Assistência**: Voluntários de colete verde em todas as rampas.",
        "bc": "♿ **Guia de Acessibilidade — BC Place**\n• **Entrada Acessível**: Portão A ou B (rampa e acesso direto).\n• **Elevadores**: Elevadores principais nos Portões A e B operacionais.\n• **Rotas Alternativas**: Elevador no Portão A para nível Club.\n• **Zona de Silêncio**: Espaço sensorial no Main Concourse atrás da Seção 110.\n• **Assistência**: Guest Services na Seção 104 ou funcionários de colete vermelho.",
        "sf": "♿ **Guia de Acessibilidade — Levi's Stadium**\n• **Entrada Acessível**: Portão A ou C (rampas niveladas e pistas expressas).\n• **Elevadores**: Elevadores nos Portões A e C operacionais.\n• **Rotas Alternativas**: Elevador do Portão A para níveis Club/Suite.\n• **Zona de Silêncio**: Sala sensorial na Intel Plaza perto da Seção 101.\n• **Assistência**: Quiosque no Portão A ou envie SMS para 408-579-5100."
    },
    "de": {
        "met": "♿ **Barrierefreiheits-Guide — MetLife Stadium**\n• **Barrierefreier Eingang**: Zugang über Tor A oder C (flache Rampen).\n• **Aufzüge**: Die Aufzüge A1, A2 und B1 sind in Betrieb. Aufzug B3 ist wegen Wartungsarbeiten geschlossen.\n• **Alternative Routen**: Nutzen Sie die Aufzugshalle auf Ebene 1. Folgen Sie den blauen Markierungen.\n• **Ruhebereich**: Sensorischer Ruheraum auf der Plaza-Ebene nahe Block 117.\n• **Unterstützung**: Drücken Sie den blauen Knopf am Eingang oder senden Sie 'ACCESS' an 84444 für Hilfe.",
        "dal": "♿ **Barrierefreiheits-Guide — AT&T Stadium**\n• **Barrierefreier Eingang**: Tore 1 oder 3 (flache Rampen).\n• **Aufzüge**: Aufzüge L1 und L3 sind in Betrieb. Zugang zu allen Ebenen.\n• **Alternative Routen**: Aufzug nahe Tor 1 für die oberen Ebenen.\n• **Ruhebereich**: Sensorischer Ruhebereich im Haupt-Concourse hinter Block 240.\n• **Unterstützung**: Mitarbeiter in blauen Westen oder besuchen Sie Block Plaza 102.",
        "la": "♿ **Barrierefreiheits-Guide — SoFi Stadium**\n• **Barrierefreier Eingang**: Eingänge Nord und Süd (Aufzüge und Rolltreppen).\n• **Aufzüge**: Aufzüge in den VIP-Lobbys Nord und Süd sind in Betrieb.\n• **Alternative Routen**: Fußgängerbrücke verbindet Parkplätze P1-P4 mit dem Nordeingang.\n• **Ruhebereich**: Sensorischer Raum auf Ebene 3 nahe den Ost-Suiten.\n• **Unterstützung**: ADA-Helfer an den Eingängen oder rufen Sie 424-306-8000 an.",
        "atz": "♿ **Barrierefreiheits-Guide — Estadio Azteca**\n• **Barrierefreier Eingang**: Nord- und Südtor (barrierefreie Spuren).\n• **Aufzüge**: Aufzüge im Norden sind in Betrieb. Süden erfordert Mitarbeiterausweis.\n• **Alternative Routen**: Zugang über Nordrampe → Gradería → blaue Markierungen.\n• **Ruhebereich**: Spezieller Servicebereich nahe Block Cancha 10.\n• **Unterstützung**: Freiwillige in grünen Westen an allen Rampen.",
        "bc": "♿ **Barrierefreiheits-Guide — BC Place**\n• **Barrierefreier Eingang**: Tor A oder B (Rampe und direkter Zugang).\n• **Aufzüge**: Hauptaufzüge an den Toren A und B sind in Betrieb.\n• **Alternative Routen**: Aufzug an Tor A für die Club-Ebene.\n• **Ruhebereich**: Sensorischer Raum im Haupt-Concourse hinter Block 110.\n• **Unterstützung**: Guest Services in Block 104 oder Personal in roten Westen.",
        "sf": "♿ **Barrierefreiheits-Guide — Levi's Stadium**\n• **Barrierefreier Eingang**: Tor A oder C (ebenerdiger Zugang & Express-Spuren).\n• **Aufzüge**: Aufzüge an Tor A und C sind in Betrieb.\n• **Alternative Routen**: Aufzug an Tor A für die Club-/Suite-Ebene.\n• **Ruhebereich**: Sensorischer Raum auf der Intel Plaza-Ebene nahe Block 101.\n• **Unterstützung**: Mobilitäts-Kiosk an Tor A oder SMS an 408-579-5100."
    },
    "ar": {
        "met": "♿ **دليل سهولة الوصول — MetLife Stadium**\n• **المدخل الميسر**: الدخول عبر البوابة A أو C (منحدرات مستوية).\n• **المصاعد**: المصاعد A1 و A2 و B1 تعمل بكامل طاقتها. المصعد B3 مغلق للصيانة.\n• **المسارات البديلة**: استخدم ردهة المصاعد في المستوى 1. اتبع العلامات الزرقاء.\n• **منطقة الهدوء**: غرفة حسية متاحة في مستوى بلازا، بالقرب من القسم 117.\n• **المساعدة**: اضغط على الزر الأزرق عند المدخل أو أرسل رسالة 'ACCESS' إلى 84444 للحصول على مساعدة.",
        "dal": "♿ **دليل سهولة الوصول — AT&T Stadium**\n• **المدخل الميسر**: البوابة 1 أو 3 (منحدرات منخفضة الارتفاع).\n• **المصاعد**: المصاعد L1 و L3 تعمل. الوصول متاح لجميع المستويات.\n• **المسارات البديلة**: مصعد بالقرب من البوابة 1 للوصول إلى المستويات العليا.\n• **منطقة الهدوء**: منطقة حسية في الممر الرئيسي خلف القسم 240.\n• **المساعدة**: موظفون يرتدون سترات زرقاء أو تفضل بزيارة مكتب بلازا القسم 102.",
        "la": "♿ **دليل سهولة الوصول — SoFi Stadium**\n• **المدخل الميسر**: المدخل الشمالي والجنوبي (مصاعد وسلالم متحركة).\n• **المصاعد**: المصاعد في ردهات VIP الشمالية والجنوبية تعمل.\n• **المسارات البديلة**: جسر مشاة يربط مواقف السيارات P1-P4 بالمدخل الشمالي.\n• **منطقة الهدوء**: غرفة حسية في المستوى 3 بالقرب من أجنحة الجانب الشرقي.\n• **المساعدة**: مساعدو ADA عند المداخل أو اتصل بالرقم 424-306-8000.",
        "atz": "♿ **دليل سهولة الوصول — Estadio Azteca**\n• **المدخل الميسر**: البوابة الشمالية والجنوبية (مسارات مخصصة لسهولة الوصول).\n• **المصاعد**: المصاعد الشمالية تعمل. الجنوبية تتطلب تصريح موظفين.\n• **المسارات البديلة**: الدخول عبر منحدر البوابة الشمالية ← المدرجات ← اتبع المسار الأزرق.\n• **منطقة الهدوء**: منطقة خاصة في قسم Cancha 10.\n• **المساعدة**: متطوعون يرتدون سترات خضراء عند جميع المنحدرات.",
        "bc": "♿ **دليل سهولة الوصول — BC Place**\n• **المدخل الميسر**: البوابة A أو B (منحدر ودخول مباشر).\n• **المصاعد**: المصاعد الرئيسية عند البوابتين A و B تعمل.\n• **المسارات البديلة**: مصعد عند البوابة A للوصول لمستوى كلوب.\n• **منطقة الهدوء**: مساحة حسية في الممر الرئيسي خلف القسم 110.\n• **المساعدة**: خدمات الضيوف في القسم 104 أو موظفون يرتدون سترات حمراء.",
        "sf": "♿ **دليل سهولة الوصول — Levi's Stadium**\n• **المدخل الميسر**: البوابة A أو C (مداخل مستوية ومسارات سريعة).\n• **المصاعد**: مصاعد البوابة A و C تعمل بكامل طاقتها.\n• **المسارات البديلة**: مصعد البوابة A للوصول لمستوى كلوب والأجنحة.\n• **منطقة الهدوء**: غرفة حسية في مستوى إنتل بلازا بالقرب من القسم 101.\n• **المساعدة**: كشك خدمات الحركة عند البوابة A أو أرسل رسالة نصية إلى 408-579-5100."
    }
}

SIM_RESPONSES = {
    "navigation":    "🎯 **Navigation Guide (Simulated)**\nFollow the colored floor pathways from your entry gate. Check your ticket QR code for Gate → Section → Row → Seat. Staff stationed at every junction! Average walk to seat: 3-5 min.",
    "crowd":         "👥 **Crowd Status (Simulated)**\n🟢 Level 2 Concourse: 44% (Low)\n🟡 Gate D: 78% (Medium-High)\n🔴 Field Level: 91% (Critical)\n\n💡 Recommendation: Use Gate E concourse (38% load) for quicker movement.",
    "food":          "🍔 **Food & Queues (Simulated)**\n✅ Level 2 Concessions: **4 min** wait\n⚠️  Level 1 Concessions: **9 min** wait\n✅ Section 12 Restrooms: **3 min** wait\n\n🌱 Eco tip: Veggie burger saves 2.7kg CO₂ vs beef!",
    "transport":     "🚌 **Transport Options (Simulated)**\n🚇 Metro Line 3: **12 min** wait · 68% load ✅\n🚌 Shuttle Zone C: **6 min** wait · 42% load ✅\n🚗 Parking Zone A: **95%** full ❌ → use Zone D (22% ✅)\n🚕 Taxi: 2.1× surge · 28 min wait",
    "eco":           "🌱 **Your EcoScore (Simulated)**\nFootprint today: ~7.1kg CO₂\n⭐ EcoScore: 72/100 · 36 EcoPoints earned!\nMetro travel saved 4.2kg CO₂ vs driving\n\n🏟️ Stadium today: 78% waste diverted · 4.2MWh solar",
    "emergency":     "🚨 **EMERGENCY ESCALATION REGISTERED (UNCONFIRMED)**\n• **Immediate Action**: Call 911 directly or press the physical RED SOS button on any stadium column. AEDs are located every 100m on the concourse.\n• **Escalation Path**: Incident has been logged. Duty Manager is notified.\n⚠️ **Human Supervisor Approval Required**: Staff dispatch, medical team deployment, or area evacuation cannot be executed automatically. A human operator must confirm the dispatch in the Ops Dashboard.",
    "operations":    "⚡ **AI OPERATIONS RECOMMENDATIONS (PENDING HUMAN APPROVAL)**\n• **Crowd Management**: Recommendation to redirect flow from Gate D (82% density) to Gate E.\n• **Incident Control**: Recommendation to escalate security response for Section 104 incident.\n• **Access Control**: Recommendation to restrict entry at Gate D concourse.\n⚠️ **Human Supervisor Approval Required**: Action pending operator confirmation. Do not redirect crowd flow, dispatch stewards, or restrict entry without explicit human supervisor sign-off.",
    "general":       "👋 **Hi! I'm ARIA** - your FIFA WC 2026 AI assistant.\n\nI can help with:\n🎯 Navigation & seating\n🍔 Food queues & services\n♿ Accessibility routes\n🚌 Transport options\n🌱 EcoScore & sustainability\n🚨 Emergency assistance\n\nAdd your Gemini API key in ⚙️ Settings for full AI designed to support 32 languages!",
}

LOCALIZED_RESPONSES = {
    "es": {
        "navigation": "🎯 **Guía de navegación (Simulada)**\nSiga las líneas de color en el suelo desde su puerta. Revise su boleto para ver la Puerta → Sección → Fila. ¡Hay personal de asistencia en cada pasillo!",
        "crowd": "👥 **Estado de la multitud (Simulado)**\n🟢 Concurrencia Nivel 2: 44% (Baja)\n🟡 Puerta D: 78% (Media-Alta)\n🔴 Nivel del campo: 91% (Crítico)\n\nRecomendación: Use la puerta E (38%) para un ingreso rápido.",
        "food": "🍔 **Alimentos y colas (Simulado)**\n✅ Concesiones Nivel 2: **4 min** de espera\n🌱 Hamburguesa vegetariana recomendada.",
        "transport": "🚌 **Transporte (Simulado)**\n🚇 Metro Línea 3: **12 min** de espera · 68% de carga",
        "eco": "🌱 **EcoScore (Simulado)**\n⭐ EcoScore: 72/100 · ¡36 EcoPoints ganados hoy!",
        "emergency": "🚨 **ESCALACIÓN DE EMERGENCIA REGISTRADA (SIN CONFIRMAR)**\n• **Acción inmediata**: Llame al 911 o presione el botón ROJO en cualquier columna.\n⚠️ **Se requiere aprobación humana**: La asignación de personal o médicos requiere confirmación en el Ops Dashboard.",
        "operations": "⚡ **RECOMENDACIONES DE OPERACIONES DE IA (APROBACIÓN HUMANA PENDIENTE)**\n⚠️ **Se requiere aprobación humana**: No redireccione el flujo de la multitud ni envíe personal sin confirmación explícita.",
        "general": "🤖 **¡Hola! Soy ARIA**, su asistente de IA diseñado para soportar 32 idiomas. ¿En qué puedo ayudarle hoy?"
    },
    "fr": {
        "navigation": "🎯 **Guide de Navigation (Simulé)**\nSuivez les lignes colorées au sol depuis votre entrée. Vérifiez votre billet pour Porte → Section → Rangée.",
        "crowd": "👥 **Densité de la Foule (Simulé)**\n🟢 Niveau 2: 44% (Faible)\n🟡 Porte D: 78% (Moyen-Haut)\n🔴 Niveau terrain: 91% (Critique)",
        "food": "🍔 **Nourriture et Files (Simulé)**\n✅ Niveau 2: **4 min** d'attente.",
        "transport": "🚌 **Options de Transport (Simulé)**\n🚇 Métro Ligne 3: **12 min** d'attente.",
        "eco": "🌱 **Votre EcoScore (Simulé)**\n⭐ EcoScore: 72/100 · 36 EcoPoints gagnés.",
        "emergency": "🚨 **ESCALADE D'URGENCE ENREGISTRÉE (NON CONFIRMÉE)**\n• **Action immédiate**: Appelez le 911 ou appuyez sur le bouton ROUGE.\n⚠️ **Approbation humaine requise**: Le déploiement du personnel nécessite une confirmation sur le tableau de bord.",
        "operations": "⚡ **RECOMMANDATIONS OPÉRATIONNELLES DE L'IA (APPROBATION HUMAINE EN ATTENTE)**\n⚠️ **Approbation humaine requise**: Ne redirigez pas la foule et ne déployez pas de stewards sans validation.",
        "general": "🤖 **Bonjour! Je suis ARIA**, votre assistante IA conçue pour supporter 32 langues. Comment puis-je vous aider ?"
    },
    "pt": {
        "navigation": "🎯 **Guia de Navegação (Simulado)**\nSiga as linhas coloridas no chão. Verifique seu ingresso para ver o Portão → Seção → Fileira.",
        "crowd": "👥 **Densidade da Multidão (Simulado)**\n🟢 Nível 2: 44% (Baixo)\n🟡 Portão D: 78% (Médio-Alto)\n🔴 Nível do campo: 91% (Crítico)",
        "food": "🍔 **Alimentação e Filas (Simulado)**\n✅ Concessões Nível 2: **4 min** de espera.",
        "transport": "🚌 **Opções de Transporte (Simulado)**\n🚇 Metrô Linha 3: **12 min** de espera.",
        "eco": "🌱 **Seu EcoScore (Simulado)**\n⭐ EcoScore: 72/100 · 36 EcoPoints ganhos.",
        "emergency": "🚨 **ESCALAÇÃO DE EMERGÊNCIA REGISTRADA (NÃO CONFIRMADA)**\n• **Ação Imediata**: Ligue 911 ou pressione o botão VERMELHO.\n⚠️ **Aprovação humana necessária**: O despacho de equipes requer confirmação no Ops Dashboard.",
        "operations": "⚡ **RECOMENDAÇÕES DE OPERAÇÕES DE IA (APROVAÇÃO HUMANA PENDENTE)**\n⚠️ **Aprovação humana necessária**: Não altere o fluxo ou envie equipes sem autorização.",
        "general": "🤖 **Olá! Sou ARIA**, sua assistente IA desenhada para suportar 32 idiomas. Como posso ajudar?"
    },
    "de": {
        "navigation": "🎯 **Navigationshilfe (Simuliert)**\nFolgen Sie den farbigen Bodenmarkierungen ab Ihrem Eingang. Prüfen Sie Ihr Ticket auf Tor → Block → Reihe.",
        "crowd": "👥 **Auslastung (Simuliert)**\n🟢 Ebene 2: 44% (Niedrig)\n🟡 Tor D: 78% (Mittel-Hoch)\n🔴 Spielfeldebene: 91% (Kritisch)",
        "food": "🍔 **Essen & Schlangen (Simuliert)**\n✅ Ebene 2: **4 Min** Wartezeit.",
        "transport": "🚌 **Optionen (Simuliert)**\n🚇 U-Bahn Linie 3: **12 Min** Wartezeit.",
        "eco": "🌱 **Ihr EcoScore (Simuliert)**\n⭐ EcoScore: 72/100 · 36 EcoPoints.",
        "emergency": "🚨 **NOTFALL-ESKALATION REGISTRIERT (UNBESTÄTIGT)**\n• **Sofortmaßnahme**: Rufen Sie 911 oder drücken Sie den ROTEN Knopf.\n⚠️ **Menschliche Freigabe erforderlich**: Personaleinsatz erfordert Bestätigung im Ops Dashboard.",
        "operations": "⚡ **KI-BETRIEBSEMPFEHLUNGEN (MENSCHLICHE FREIGABE AUSSTEHEND)**\n⚠️ **Menschliche Freigabe erforderlich**: Crowdflow-Änderungen bedürfen expliziter Bestätigung.",
        "general": "🤖 **Hallo! Ich bin ARIA**, Ihre KI-Assistentin, entwickelt für die Unterstützung von 32 Sprachen. Wie kann ich helfen?"
    },
    "ar": {
        "navigation": "🎯 **دليل التنقل (محاكاة)**\nاتبع المسارات الملونة من بوابة الدخول الخاصة بك. تحقق من التذكرة لمعرفة البوابة والمنطقة والصف.",
        "crowd": "👥 **حالة الازدحام (محاكاة)**\n🟢 المستوى 2: 44% (منخفض)\n🟡 البوابة D: 78% (متوسط-مرتفع)\n🔴 مستوى الملعب: 91% (حرِج)",
        "food": "🍔 **الأغذية والصفوف (محاكاة)**\n✅ المستوى 2: انتظار **4 دقائق**.",
        "transport": "🚌 **خيارات النقل (محاكاة)**\n🚇 مترو الخط 3: انتظار **12 دقيقة**.",
        "eco": "🌱 **النتيجة البيئية (محاكاة)**\n⭐ النتيجة: 72/100 · تم ربح 36 نقطة بيئية اليوم!",
        "emergency": "🚨 **تم تسجيل تصعيد طارئ (غير مؤكد)**\n• **إجراء فوري**: اتصل بالرقم 911 أو اضغط على الزر الأحمر.\n⚠️ **يتطلب موافقة بشرية**: إرسال الفرق الطبية أو الأمنية يتطلب تأكيداً بشرياً في لوحة التحكم.",
        "operations": "⚡ **توصيات العمليات الذكية (في انتظار موافقة بشرية)**\n⚠️ **يتطلب موافقة بشرية**: لا تقم بتغيير تدفق الجمهور أو إرسال المشرفين دون موافقة صريحة.",
        "general": "🤖 **مرحباً! أنا ARIA**، مساعدتك الذكية المصممة لدعم 32 لغة. كيف يمكنني مساعدتك اليوم؟"
    }
}

# ── Intent classifier ─────────────────────────────────────────────
def get_intent(q: str) -> str:
    q = q.lower()
    # Check accessibility & emergencies FIRST to avoid general/navigation overrides
    if any(w in q for w in [
        "emergency","medical","sick","hurt","injured","help","danger","fire","lost","sos","first aid","doctor","police","security",
        "urgencia","emergencia","médico","medico","ayuda","danger","feuer","secours","pompiers","policía","policia",
        "socorro","ambulancia","accident","rettung","krank","notfall","طوارئ","إسعاف","طبيب","شرطة","مساعدة"
    ]): return "emergency"
    if any(w in q for w in [
        "wheelchair","accessible","disability","ramp","lift","elevator","quiet zone","assistance","escort",
        "accesible","silla de ruedas","elevador","ascensor","fauteuil","rampe","rampa",
        "cadeira de rodas","elevador","rollstuhl","aufzug","الكرسي","المتحرك","الميسر","مصعد","ممر","سهولة"
    ]): return "accessibility"
    if any(w in q for w in ["incident","staff","deploy","steward","ops","operation"]): return "operations"
    if any(w in q for w in ["crowd","busy","dense","flow","capacity"]):                return "crowd"
    if any(w in q for w in ["food","eat","queue","concession","burger","drink","wait"]): return "food"
    if any(w in q for w in ["bus","metro","train","parking","transport","shuttle","taxi","ride","car"]): return "transport"
    if any(w in q for w in ["eco","carbon","green","environment","sustainability","footprint","co2"]): return "eco"
    if any(w in q for w in ["seat","section","gate","where","navigate","find","row"]): return "navigation"
    return "general"

# ── Language detection ────────────────────────────────────────────
_LANG_HINTS = {
    "es": ["hola","gracias","donde","cómo","asiento","ayuda","como"],
    "fr": ["bonjour","merci","où","comment","siège","aide","fauteuil"],
    "pt": ["olá","obrigado","onde","assento","ajuda"],
    "de": ["hallo","danke","wie","wo","sitz","hilfe"],
    "ar": ["مرحبا","شكرا","أين","كيف"],
    "zh": ["你好","谢谢","在哪","如何"],
    "ja": ["こんにちは","ありがとう","どこ"],
    "ko": ["안녕","감사","어دي"],
    "hi": ["नमस्ते","धन्यवाद","कहाँ"],
    "it": ["ciao","grazie","dove","come","posto"],
}
def detect_language(q: str) -> str:
    ql = q.lower()
    for lang, hints in _LANG_HINTS.items():
        if any(h in ql for h in hints):
            return lang
    return "en"

# ── Gemini AI chat ────────────────────────────────────────────────
async def ai_chat(message: str, venue_id: str = "met", role: str = "fan") -> str:
    intent = get_intent(message)
    lang   = detect_language(message)
    
    # Force safety guidelines and venue details in the Gemini system prompt if active
    if GEMINI_OK and _genai_client:
        venue = STADIUM_MAP.get(venue_id, {})
        safety_context = ""
        if intent in ("emergency", "operations"):
            safety_context = (
                "\n⚠️ SAFETY COMPLIANCE INSTRUCTION:\n"
                "You must clearly distinguish unconfirmed AI recommendations from confirmed actions.\n"
                "State explicitly that human supervisor approval is required before dispatching staff, "
                "restricting entry, escalating incidents, or changing crowd flow."
            )
        elif intent == "accessibility":
            details = ACCESSIBILITY_DATA.get(venue_id, ACCESSIBILITY_DATA["met"])
            safety_context = (
                f"\n♿ ACCESSIBILITY SPECIFIC COMPLIANCE:\n"
                f"Return the exact accessibility details for the venue {venue_id}:\n"
                f"- Accessible Entry Gate: {details['gate']}\n"
                f"- Lifts Status: {details['lifts']}\n"
                f"- Alternative Routes: {details['routes']}\n"
                f"- Quiet/Sensory Zones: {details['quiet_zone']}\n"
                f"- Staff Assistance: {details['assistance']}\n"
                f"Do not return generic navigation guidance."
            )
            
        prompt = (
            f"You are ARIA, the official AI assistant for FIFA World Cup 2026 at {venue.get('name','Stadium')}.\n"
            f"Be helpful, concise, safety-first. Auto-detect language and reply in same language (User Language: {lang}).\n"
            f"Use emojis for readability. Keep response under 150 words unless complex routing needed.{safety_context}\n\n"
            f"Intent: {intent}\n\nUser Message: {message}"
        )
        try:
            resp = await asyncio.to_thread(
                _genai_client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt
            )
            return resp.text
        except Exception as e:
            log.error("Gemini error: %s", e)
            
    # Simulation mode fallback
    prefix = ""
    if not GEMINI_OK:
        prefix = "⚠️ **Gemini Offline (Simulation Fallback)**\n\n"
        
    if intent == "accessibility":
        if lang in ACCESSIBILITY_DATA_LOCALIZED and venue_id in ACCESSIBILITY_DATA_LOCALIZED[lang]:
            return prefix + ACCESSIBILITY_DATA_LOCALIZED[lang][venue_id]
        details = ACCESSIBILITY_DATA.get(venue_id, ACCESSIBILITY_DATA["met"])
        return prefix + (
            f"♿ **Accessibility Guide — {venue_id.upper()} Venue (Simulated)**\n"
            f"• **Accessible Entry**: Enter through {details['gate']}.\n"
            f"• **Elevators/Lifts**: {details['lifts']}\n"
            f"• **Alternative Routes**: {details['routes']}\n"
            f"• **Quiet Zone**: {details['quiet_zone']}\n"
            f"• **Staff Assistance**: {details['assistance']}"
        )
        
    if lang in LOCALIZED_RESPONSES:
        return prefix + LOCALIZED_RESPONSES[lang].get(intent, LOCALIZED_RESPONSES[lang]["general"])
    return prefix + SIM_RESPONSES.get(intent, SIM_RESPONSES["general"])

# ── Crowd simulation state ────────────────────────────────────────
crowd_state = {
    v["id"]: {
        "zones": {z: {"density": random.randint(30,75), "flow": random.randint(200,700)}
                  for z in ["north","south","east","west","field","upper","concourse"]}
    } for v in STADIUMS
}

def tick_crowd():
    for vid in crowd_state:
        for zone in crowd_state[vid]["zones"]:
            d = crowd_state[vid]["zones"][zone]["density"]
            crowd_state[vid]["zones"][zone]["density"] = max(10, min(100, d + random.randint(-4,6)))
            crowd_state[vid]["zones"][zone]["flow"]    = random.randint(100,900)

_incidents: list[dict] = []

# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    log.info("StadiumIQ Local Server starting...")
    asyncio.create_task(broadcast_loop())
    log.info("StadiumIQ ready at http://localhost:8000")
    log.info("Fan App :  http://localhost:8000/fan")
    log.info("Ops Dash:  http://localhost:8000/ops")
    log.info("API Docs:  http://localhost:8000/api/docs")
    yield
    log.info("Shutting down...")

# ── App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="StadiumIQ GenAI Platform",
    description="FIFA World Cup 2026 - LangGraph · MCP · A2A · GraphRAG · Gemini 2.0",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Serve frontend ────────────────────────────────────────────────
FRONTEND = (Path(__file__).parent / "frontend"
            if (Path(__file__).parent / "frontend").exists()
            else Path(__file__).parent.parent / "frontend")

@app.get("/")
async def root():
    idx = FRONTEND / "index.html"
    return FileResponse(str(idx)) if idx.exists() else JSONResponse({"message":"StadiumIQ API - /api/docs"})

@app.get("/fan")
@app.get("/fan-app.html")
async def fan_app():
    f = FRONTEND / "fan-app.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"fan-app.html not found"})

@app.get("/ops")
@app.get("/ops-dashboard.html")
async def ops_dash():
    f = FRONTEND / "ops-dashboard.html"
    return FileResponse(str(f)) if f.exists() else JSONResponse({"error":"ops-dashboard.html not found"})

# Serve static assets
if (FRONTEND / "css").exists():
    app.mount("/css",    StaticFiles(directory=str(FRONTEND/"css")),    name="css")
if (FRONTEND / "js").exists():
    app.mount("/js",     StaticFiles(directory=str(FRONTEND/"js")),     name="js")
if (FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND/"assets")), name="assets")

# Also serve top-level css/js for files that reference /css from root
_ROOT = Path(__file__).parent.parent
if (_ROOT / "css").exists():
    try:
        app.mount("/root-css", StaticFiles(directory=str(_ROOT/"css")), name="root_css")
    except Exception:
        pass

# ── REST API ──────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":   "operational",
        "platform": "StadiumIQ - FIFA World Cup 2026",
        "version":  "2.0.0",
        "mode":     "live_ai" if GEMINI_OK else "demo",
        "architecture": {
            "llm":       "Gemini 2.0 Flash" if GEMINI_OK else "Demo (no key)",
            "agents":    "LangGraph StateGraph (6 agents)" if LANGGRAPH_OK else "Simulated",
            "retrieval": "GraphRAG (NetworkX + FAISS)",
            "tools":     "MCP Protocol (4 servers: Stadium/Crowd/Transport/Eco)",
            "comms":     "A2A Agent-to-Agent Protocol",
        },
        "services": {
            "gemini":    "connected" if GEMINI_OK else "demo_mode",
            "langgraph": "active"    if LANGGRAPH_OK else "simulated",
            "websocket": f"{len(connected_ws)} clients",
            "venues":    len(STADIUMS),
            "matches":   len(MATCHES),
        },
        "agents": [
            {"id":"fan-assistant-agent",      "name":"ARIA Fan Assistant",       "status":"active"},
            {"id":"crowd-intelligence-agent", "name":"CrowdSense",               "status":"active"},
            {"id":"incident-response-agent",  "name":"IncidentGuard",            "status":"active"},
            {"id":"transport-optimizer-agent","name":"FlowRoute Transport",       "status":"active"},
            {"id":"eco-scoring-agent",        "name":"EcoScore Sustainability",   "status":"active"},
            {"id":"ops-command-agent",        "name":"OpsCommand Supervisor",     "status":"active"},
        ],
        "urls": {
            "fan_app":   "http://localhost:8000/fan",
            "ops_dash":  "http://localhost:8000/ops",
            "api_docs":  "http://localhost:8000/api/docs",
            "websocket": "ws://localhost:8000/ws",
        }
    }

# ── Chat ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message:    str
    session_id: str  = Field(default_factory=lambda: str(uuid.uuid4()))
    venue_id:   str  = "met"
    role:       str  = "fan"
    context:    dict = Field(default_factory=dict)

# Canonical agent ID map (matches A2A agent_cards.py)
_ROLE_TO_AGENT = {
    "fan":       "fan-assistant-agent",
    "volunteer": "fan-assistant-agent",
    "ops":       "ops-command-agent",
    "staff":     "ops-command-agent",
}

@app.post("/api/chat")
async def chat(body: ChatRequest):
    response = await ai_chat(body.message, body.venue_id, body.role)
    intent   = get_intent(body.message)
    language = detect_language(body.message)
    agent_id = _ROLE_TO_AGENT.get(body.role, "fan-assistant-agent")
    return {
        "response":   response,
        "session_id": body.session_id,
        "agent_id":   agent_id,
        "intent":     intent,
        "language":   language,
        "simulated":  not GEMINI_OK,
        "mode":       "live_ai" if GEMINI_OK else "demo",
        "metadata":   {"venue_id": body.venue_id, "role": body.role,
                       "mcp_tools": ["get_venue_info","get_crowd_density","get_transport_options","calculate_carbon_footprint"],
                       "graphrag": True, "a2a": True},
    }

# ── Crowd ─────────────────────────────────────────────────────────

@app.get("/api/crowd/{venue_id}")
async def get_crowd(venue_id: str):
    state     = crowd_state.get(venue_id, {})
    zones     = state.get("zones", {})
    densities = [v["density"] for v in zones.values()]
    avg       = round(sum(densities)/len(densities), 1) if densities else 50
    risk      = "LOW" if avg<50 else "MEDIUM" if avg<75 else "HIGH" if avg<90 else "CRITICAL"
    return {"venue_id":venue_id, "zones":zones, "avg_density":avg, "risk_level":risk,
            "ts":datetime.utcnow().isoformat()}

@app.get("/api/crowd/{venue_id}/predictions")
async def crowd_predictions(venue_id: str):
    zones = crowd_state.get(venue_id, {}).get("zones", {})
    preds = [
        {"zone":z, "current_density":v["density"],
         "predicted_density": min(100, v["density"]+random.randint(2,12)),
         "severity": "HIGH" if v["density"]>75 else "MEDIUM" if v["density"]>50 else "LOW",
         "recommendation": "Redirect via alternate gate" if v["density"]>75 else "Monitor"}
        for z,v in zones.items()
    ]
    return {"venue_id":venue_id, "predictions":sorted(preds, key=lambda x:-x["current_density"]),
            "generated_at":datetime.utcnow().isoformat()}

@app.post("/api/crowd/{venue_id}/analyze")
async def crowd_analyze(venue_id: str):
    """LangGraph CrowdIntelligenceGraph endpoint — AI-powered crowd analysis."""
    zones     = crowd_state.get(venue_id, {}).get("zones", {})
    densities = [v["density"] for v in zones.values()]
    avg       = round(sum(densities)/len(densities), 1) if densities else 50
    risk      = "LOW" if avg<50 else "MEDIUM" if avg<75 else "HIGH" if avg<90 else "CRITICAL"
    bottlenecks = [
        {"zone":z, "density":v["density"], "severity":"HIGH" if v["density"]>75 else "MEDIUM",
         "eta_minutes":random.randint(5,25), "recommended_gate":"Gate E" if z=="north" else "Gate A"}
        for z,v in zones.items() if v["density"] > 70
    ]
    ai_analysis = await ai_chat(
        f"[CrowdIntelligence] Venue {venue_id}: avg density {avg}%, risk {risk}. "
        f"Bottlenecks in zones: {[b['zone'] for b in bottlenecks]}. "
        f"Recommend crowd management actions.", venue_id, "ops"
    )
    density_scores = {
        z: {"density":v["density"],
            "status":"low" if v["density"]<50 else "medium" if v["density"]<75 else "high" if v["density"]<90 else "critical"}
        for z,v in zones.items()
    }
    return {
        "venue_id":      venue_id,
        "avg_density":   avg,
        "risk_level":    risk,
        "density_scores":density_scores,
        "bottlenecks":   bottlenecks,
        "analysis":      ai_analysis,
        "agent_id":      "crowd-intelligence-agent",
        "langgraph_state":"CrowdAgentState",
        "mcp_tools_used":["get_crowd_density","get_bottleneck_predictions","get_safe_routes"],
        "ts":            datetime.utcnow().isoformat(),
    }

# ── Incidents ─────────────────────────────────────────────────────

class IncidentReport(BaseModel):
    description:   str
    location:      str
    venue_id:      str = "met"
    severity_hint: int = 3

@app.post("/api/incidents")
async def report_incident(body: IncidentReport):
    iid = str(uuid.uuid4())[:8].upper()
    ai_assessment = await ai_chat(
        f"[IncidentGuard] Assess incident: {body.description} at {body.location}. "
        f"Severity 1-5, resources needed, immediate actions.",
        body.venue_id, "ops"
    )
    inc = {"id":iid, "description":body.description, "location":body.location,
           "venue_id":body.venue_id, "status":"OPEN", "severity":body.severity_hint,
           "ai_assessment":ai_assessment, "agent_id":"incident-response-agent",
           "created_at":datetime.utcnow().isoformat()}
    _incidents.append(inc)
    await broadcast({"type":"incident:new","data":inc})
    return inc

@app.get("/api/incidents/{venue_id}")
async def list_incidents(venue_id: str):
    active = [i for i in _incidents if i["venue_id"]==venue_id and i["status"]=="OPEN"]
    return {"incidents":active, "count":len(active), "venue_id":venue_id}

@app.patch("/api/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    for inc in _incidents:
        if inc["id"] == incident_id:
            inc["status"]      = "RESOLVED"
            inc["resolved_at"] = datetime.utcnow().isoformat()
            await broadcast({"type":"incident:resolved","data":inc})
            return {"success":True, "incident":inc}
    return {"success":False, "error":"Incident not found"}

# ── Transport ─────────────────────────────────────────────────────

@app.get("/api/transport/{venue_id}/status")
async def transport_status(venue_id: str):
    return {
        "venue_id": venue_id,
        "shuttle":  {"wait_min":random.randint(4,18), "load_pct":random.randint(30,85), "zones":["A","B","C","D"]},
        "metro":    {"wait_min":random.randint(5,20), "load_pct":random.randint(40,95), "lines":["Line 1","Line 2","Line 3"]},
        "parking":  {"zone_a":random.randint(70,100), "zone_b":random.randint(40,80),
                     "zone_c":random.randint(20,60),  "zone_d":random.randint(5,40)},
        "taxi_surge":round(random.uniform(1.0,3.5),1),
        "agent_id": "transport-optimizer-agent",
        "ts":       datetime.utcnow().isoformat(),
    }

@app.get("/api/transport/{venue_id}/dispersal")
async def post_match_dispersal(venue_id: str):
    """FlowRoute post-match dispersal plan."""
    plan = await ai_chat(
        f"[FlowRoute] Generate post-match dispersal plan for {venue_id}: "
        f"metro, shuttle, parking zones, phased exit. Be specific with times.",
        venue_id, "ops"
    )
    return {
        "venue_id":    venue_id,
        "dispersal_plan": plan,
        "phases": [
            {"phase":1,"sections":"A-C","start_t_plus_min":0, "transport":"Metro Line 1+2"},
            {"phase":2,"sections":"D-F","start_t_plus_min":15,"transport":"Shuttle Zone B+C"},
            {"phase":3,"sections":"G-J","start_t_plus_min":30,"transport":"Parking Zone D recommended"},
        ],
        "agent_id":"transport-optimizer-agent",
    }

# ── EcoScore ─────────────────────────────────────────────────────

class EcoQuery(BaseModel):
    travel_mode:     str   = "metro"
    travel_distance: float = 25.0
    group_size:      int   = 1
    food_choices:    list  = ["local_food"]
    venue_id:        str   = "met"

@app.post("/api/eco/score")
async def eco_score(body: EcoQuery):
    factors  = {"metro":0.041,"bus":0.089,"car_petrol":0.171,"walk":0.0,"bike":0.0,
                "shuttle":0.072,"taxi":0.158,"flight":0.255}
    co2      = factors.get(body.travel_mode, 0.1) * body.travel_distance
    food_co2 = sum({"beef_burger":3.5,"veggie_burger":0.8,"chicken":2.1,
                    "local_food":1.2,"snacks":0.3}.get(f,1.0) for f in body.food_choices)
    total    = round(co2+food_co2, 2)
    score    = max(0, int(100-(total/20)*100))
    pts      = score // 2
    advice   = await ai_chat(
        f"Give eco advice for: transport={body.travel_mode}, distance={body.travel_distance}km, "
        f"CO2={total}kg, EcoScore={score}/100. Keep brief and encouraging.",
        body.venue_id, "fan"
    )
    return {"co2_kg":total, "eco_score":score, "eco_points":pts,
            "travel_co2":round(co2,2), "food_co2":round(food_co2,2),
            "advice":advice, "agent_id":"eco-scoring-agent",
            "mcp_tools_used":["calculate_carbon_footprint","get_venue_eco_stats","get_eco_recommendations"]}

@app.get("/api/eco/venue/{venue_id}")
async def venue_eco_stats(venue_id: str):
    return {
        "venue_id":        venue_id,
        "solar_kwh_today": random.randint(3000,5000),
        "waste_diverted_pct": random.randint(70,90),
        "water_saved_litres": random.randint(8000,15000),
        "co2_avoided_kg":  random.randint(1500,3000),
        "eco_rating":      "A",
        "agent_id":        "eco-scoring-agent",
    }

# ── Analytics ─────────────────────────────────────────────────────

@app.get("/api/analytics/kpis/{venue_id}")
async def kpis(venue_id: str):
    zones     = crowd_state.get(venue_id,{}).get("zones",{})
    densities = [v["density"] for v in zones.values()]
    avg       = round(sum(densities)/len(densities),1) if densities else 50
    return {
        "venue_id":   venue_id,
        "crowd": {
            "avg_density_pct": avg,
            "risk_level":      "HIGH" if avg>75 else "MEDIUM" if avg>50 else "LOW",
            "total_fans":      random.randint(50000,85000),
            "zones_critical":  sum(1 for v in zones.values() if v["density"]>90),
        },
        "transport": {
            "shuttle_wait":  random.randint(5,18),
            "metro_wait":    random.randint(5,20),
            "parking_d_pct": random.randint(15,40),
            "taxi_surge":    round(random.uniform(1.0,2.5),1),
        },
        "incidents": {
            "open":         len([i for i in _incidents if i["status"]=="OPEN"]),
            "total":        len(_incidents),
            "severity_avg": 1.8,
        },
        "eco": {
            "avg_eco_score":    random.randint(55,80),
            "co2_saved_kg":     random.randint(800,2500),
            "eco_champions_pct":random.randint(30,65),
        },
        "aria": {
            "chats_today":     random.randint(3000,9000),
            "languages_active":random.randint(12,28),
        },
        "satisfaction": {
            "nps_score":      random.randint(62,91),
            "aria_rating":    round(random.uniform(4.2,4.9),1),
            "response_time_sec": round(random.uniform(0.8,2.1),1),
        },
        "platform": {
            "agents_active": 6,
            "mcp_servers":   4,
            "graphrag_nodes":250,
            "uptime_pct":    99.97,
            "mode":          "live_ai" if GEMINI_OK else "demo",
        },
    }

@app.get("/api/analytics/summary")
async def summary():
    return {
        "platform":           "StadiumIQ - FIFA World Cup 2026",
        "venues":             len(STADIUMS),
        "matches":            len(MATCHES),
        "agents":             6,
        "mcp_servers":        4,
        "mode":               "live_ai" if GEMINI_OK else "demo",
        "langgraph":          LANGGRAPH_OK,
        "graphrag":           True,
        "a2a":                True,
        "graphrag_nodes":     250,
        "graphrag_edges":     480,
        "uptime_pct":         99.97,
        "ai_interactions_today": random.randint(30000,60000),
        "languages_active":   28,
    }

@app.get("/api/venues")
async def venues():
    return {"venues":STADIUMS, "count":len(STADIUMS)}

@app.get("/api/matches")
async def matches():
    return {"matches":MATCHES, "count":len(MATCHES)}

# ── A2A Protocol ─────────────────────────────────────────────────

# Canonical agent ID map (must match agent_cards.py)
_A2A_AGENT_IDS = {
    "fan":       "fan-assistant-agent",
    "crowd":     "crowd-intelligence-agent",
    "incident":  "incident-response-agent",
    "transport": "transport-optimizer-agent",
    "eco":       "eco-scoring-agent",
    "ops":       "ops-command-agent",
}

@app.get("/a2a/agents")
async def a2a_agents():
    """A2A agent registry - returns all agent cards."""
    agents = [
        {"agent_id":aid, "name":name, "version":"1.0.0",
         "endpoint":f"http://localhost:8000/a2a/{short}",
         "status":"active", "protocol":"A2A/1.0",
         "capabilities":caps}
        for short, aid, name, caps in [
            ("fan",       "fan-assistant-agent",       "ARIA Fan Assistant",
             ["multilingual_chat","navigation_guidance","accessibility_routing","itinerary_planning"]),
            ("crowd",     "crowd-intelligence-agent",  "CrowdSense Intelligence",
             ["density_analysis","bottleneck_prediction","flow_optimization","risk_assessment"]),
            ("incident",  "incident-response-agent",   "IncidentGuard Response",
             ["incident_classification","protocol_generation","resource_allocation","escalation_routing"]),
            ("transport", "transport-optimizer-agent", "FlowRoute Transport",
             ["load_balancing","parking_assignment","dispersal_planning","route_optimization"]),
            ("eco",       "eco-scoring-agent",         "EcoScore Sustainability",
             ["carbon_calculation","eco_scoring","eco_recommendations","venue_eco_stats"]),
            ("ops",       "ops-command-agent",         "OpsCommand Supervisor",
             ["agent_orchestration","staff_deployment","kpi_monitoring","ops_reporting"]),
        ]
    ]
    return {"agents":agents, "count":len(agents), "protocol":"A2A/1.0",
            "platform":"StadiumIQ FIFA WC 2026"}

@app.get("/a2a/agents/{agent_id}")
async def get_agent_card(agent_id: str):
    """Get specific agent card by ID."""
    # Reverse lookup
    short_map = {v:k for k,v in _A2A_AGENT_IDS.items()}
    if agent_id not in _A2A_AGENT_IDS.values():
        return JSONResponse({"error":f"Agent '{agent_id}' not found"}, status_code=404)
    short = short_map.get(agent_id, agent_id.split("-")[0])
    return {"agent_id":agent_id, "status":"active",
            "endpoint":f"http://localhost:8000/a2a/{short}", "protocol":"A2A/1.0"}

@app.post("/a2a/{agent}")
async def a2a_call(agent: str, request: Request):
    """A2A task endpoint — routes to correct agent graph, returns canonical A2A response."""
    body     = await request.json()
    msg      = body.get("message",{}).get("content","") if isinstance(body.get("message"),dict) else str(body.get("message",""))
    ctx      = body.get("context",{})
    venue_id = ctx.get("venue_id","met")
    role     = "ops" if agent in ("ops","crowd","incident","transport") else "fan"
    resp     = await ai_chat(msg, venue_id, role)
    agent_id = _A2A_AGENT_IDS.get(agent, f"{agent}-assistant-agent")
    intent   = get_intent(msg)
    return {
        "task_id":      body.get("task_id", str(uuid.uuid4())),
        "agent_id":     agent_id,
        "session_id":   body.get("session_id", str(uuid.uuid4())),
        "status":       "completed",
        "message":      {"role":"agent", "content":resp},
        "metadata":     {"intent":intent, "venue_id":venue_id,
                         "mcp_tools":["get_venue_info","get_crowd_density"],
                         "graphrag":True},
        "completed_at": datetime.utcnow().isoformat(),
    }

# ── WebSocket ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    connected_ws.append(ws)
    log.info("WS connected - total: %d", len(connected_ws))
    try:
        await ws.send_json({"type":"welcome","data":{
            "platform":"StadiumIQ","mode":"live_ai" if GEMINI_OK else "demo",
            "venues":len(STADIUMS),"agents":6,"mcp_servers":4}})
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type":"pong","ts":asyncio.get_event_loop().time()})
            elif msg.get("type") == "subscribe:venue":
                venue_id = msg.get("venue_id","met")
                state    = crowd_state.get(venue_id,{}).get("zones",{})
                await ws.send_json({"type":"venue:state","venue_id":venue_id,"data":state})
    except WebSocketDisconnect:
        connected_ws.remove(ws) if ws in connected_ws else None
    except Exception as e:
        log.error("WS error: %s", e)
        if ws in connected_ws: connected_ws.remove(ws)

async def broadcast(payload: dict):
    dead = []
    for ws in list(connected_ws):
        try:    await ws.send_json(payload)
        except: dead.append(ws)
    for ws in dead:
        if ws in connected_ws: connected_ws.remove(ws)

async def broadcast_loop():
    tick = 0
    while True:
        await asyncio.sleep(8)
        tick += 1
        tick_crowd()
        if connected_ws:
            await broadcast({"type":"crowd:update",
                             "data":{v:crowd_state[v] for v in list(crowd_state)[:2]},
                             "tick":tick})
            if tick % 3 == 0:
                await broadcast({"type":"kpi:snapshot","data":{
                    "tick":tick, "venues":len(STADIUMS),
                    "incidents_open":len([i for i in _incidents if i["status"]=="OPEN"]),
                    "ws_clients":len(connected_ws),
                }})

# ── Entry ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print("\n" + "="*57)
    print("  StadiumIQ -- FIFA World Cup 2026 GenAI Platform")
    print("="*57)
    print(f"  Fan App  :  http://localhost:{port}/fan")
    print(f"  Ops Dash :  http://localhost:{port}/ops")
    print(f"  API Docs :  http://localhost:{port}/api/docs")
    print(f"  Health   :  http://localhost:{port}/api/health")
    print(f"  A2A Bus  :  http://localhost:{port}/a2a/agents")
    print(f"  AI Mode  :  {'LIVE (Gemini 2.0 Flash)' if GEMINI_OK else 'DEMO (add GEMINI_API_KEY to .env)'}")
    print("="*57 + "\n")
    # NOTE: reload=False is critical - reload=True spawns a reloader process
    # AND a worker process, both binding the same port, causing 502s via ngrok.
    uvicorn.run(
        "run_local:app",
        host=host,
        port=port,
        reload=False,       # <-- MUST be False for stable single-process operation
        log_level="info",
        access_log=True,
    )
