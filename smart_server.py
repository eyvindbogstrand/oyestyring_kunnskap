from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import re
from pathlib import Path
import requests

# VIKTIG:Importer openai på en måte som unngår proxy-problemer
try:
    from openai import OpenAI
    # Ikke initialiser klienten globalt ennå - vent til vi trenger den
    client = None
    
    def get_openai_client():
        global client
        if client is None:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY ikke satt")
            # Bruk default http_client for å unngå proxy-problemer
            client = OpenAI(api_key=api_key)
        return client
        
except ImportError:
    print("ADVARSEL: Kunne ikke importere OpenAI")
    def get_openai_client():
        raise Exception("OpenAI ikke tilgjengelig")

app = Flask(__name__)
CORS(app)
# Last inn lokal kunnskap (Wikipedia-filene)
kunnskap = {}

# Synonymer for søk
SYNONYMER = {
    'øyestyring': ['eye tracking', 'gaze', 'blikk', 'eye-tracking', 'øyesporing'],
    'øyesporing': ['eye tracking', 'gaze tracking', 'øyestyring'],
    'blikk': ['gaze', 'eye', 'øye', 'looking'],
    'hjelpemiddel': ['assistive technology', 'assistive device', 'aid', 'communication device'],
    'als': ['amyotrophic lateral sclerosis', 'amyotrofisk lateralsklerose', 'lou gehrig'],
    'kommunikasjon': ['communication', 'aac', 'augmentative', 'alternative'],
    'handicap': ['disability', 'funksjonshemning', 'impairment'],
    'tale': ['speech', 'stemme', 'voice'],
    'låst': ['locked-in', 'låsning', 'locked in'],
    'tobii': ['eye tracker', 'øyesporing', 'gaze interaction']
}

# Ord som trigger faktasjekk (øyestyring-temaet)
DOMENE_ORD = [
    'øye', 'eye', 'gaze', 'blikk', 'sporing', 'tracking', 'styring',
    'als', 'lou gehrig', 'lateralsklerose', 'scleros', 
    'hjelpemiddel', 'assistive', 'kommunikasjon', 'communication', 'aac',
    'handicap', 'disability', 'funksjonshemning', 'låsning', 'locked',
    'tobii', 'dynavox', 'irisbond', 'tellus', 'acapela',
    'stemme', 'tale', 'språk', 'language', 'snakke', 'speak'
]

def last_inn_kunnskap():
    mappe = Path("knowledge_base")
    if mappe.exists():
        for fil in mappe.glob("*.json"):
            with open(fil, 'r', encoding='utf-8') as f:
                data = json.load(f)
                kunnskap[fil.stem] = data
        print(f"Lastet inn {len(kunnskap)} lokale artikler")

def er_domenesporsmal(sporsmal):
    """Sjekk om spørsmålet handler om øyestyring/temaet"""
    sporsmal_lower = sporsmal.lower()
    return any(ord in sporsmal_lower for ord in DOMENE_ORD)

def sok_lokal_kunnskap(sporsmal):
    """Finn relevant fakta fra Wikipedia-artiklene"""
    sokeord = sporsmal.lower().split()
    
    # Utvid med synonymer
    alle_ord = set(sokeord)
    for ordet in sokeord:
        if ordet in SYNONYMER:
            alle_ord.update(SYNONYMER[ordet])
    
    resultater = []
    
    for navn, artikkel in kunnskap.items():
        for chunk in artikkel['chunks']:
            score = 0
            tekst_lower = chunk['text'].lower()
            
            for ordet in alle_ord:
                if ordet in tekst_lower:
                    score += 1
            
            if score > 0:
                resultater.append({
                    'tekst': chunk['text'],
                    'kilde': artikkel['metadata']['title'],
                    'url': artikkel['metadata']['source_url'],
                    'score': score
                })
    
    # Sorter etter relevans
    resultater.sort(key=lambda x: x['score'], reverse=True)
    return resultater[:3]

def generer_svar_med_kunnskap(sporsmal, kontekst):
    """Bruker GPT-4 med fakta fra Wikipedia som grunnlag"""
    
    system_prompt = """Du er en kunnskapsrik, empatisk og hjelpsom assistent på en nettside om øyestyring og kommunikasjonshjelpemidler. 
    Din oppgave er å hjelpe både brukere (som kan ha ALS, låsningssyndrom eller andre funksjonsnedsettelser) og pårørende/terapeuter.
    
    VIKTIG: Når du får fakta nedenfor, skal du:
    1. Bruke disse faktaene som HOVEDGRUNNLAG for svaret ditt
    2. formulere deg varmt og forståelig
    3. ALLTID oppgi kilden (Wikipedia-artikkelen) til slutt
    4. Ikke finn på fakta som ikke står i konteksten
    5. Hvis du ikke vet svaret fra konteksten, si: "Basert på tilgjengelig informasjon..." og gi generell veiledning
    
    Fakta fra pålitelige kilder:
    """ + "\n\n".join([f"Kilde: {k['kilde']}\n{k['tekst'][:500]}" for k in kontekst])
    
    try:
        # NY MÅTE - OpenAI 1.0.0:
       client_instance = get_openai_client()
response = client_instance.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": sporsmal}
            ],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Beklager, jeg har tekniske problemer. Feil: {str(e)}"

def generer_svar_generell(sporsmal):
    """Standard GPT-4 for ting utenfor temaet"""
    try:
        # NY MÅTE - OpenAI 1.0.0:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Du er en hjelpsom, vennlig assistent på en nettside om øyestyring. Du kan svare på det meste, men hvis noen spør om øyestyring, ALS eller hjelpemidler, anbefaler du dem å bruke søkefunksjonen for spesifikk informasjon."},
                {"role": "user", "content": sporsmal}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return "Beklager, jeg har problemer med å svare akkurat nå."

# Routes for å vise HTML-filer
@app.route('/')
def index():
    return send_from_directory('.', 'chat.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

@app.route('/spor', methods=['POST'])
def chat_endpoint():
    data = request.get_json()
    sporsmal = data.get('sporsmal', '')
    
    if not sporsmal:
        return jsonify({"error": "Mangler spørsmål"}), 400
    
    print(f"Mottok spørsmål: {sporsmal}")
    
    # Sjekk om dette er et domenespørsmål
    if er_domenesporsmal(sporsmal):
        print("Dette er om øyestyring - henter fakta...")
        
        # 1. Hent lokal fakta
        fakta = sok_lokal_kunnskap(sporsmal)
        
        if fakta:
            # 2. Bruk GPT-4 til å formidle faktaene pent
            svar = generer_svar_med_kunnskap(sporsmal, fakta)
            kilde_info = [{"kilde": f['kilde'], "url": f['url']} for f in fakta]
        else:
            # Ingen fakta funnet
            svar = generer_svar_med_kunnskap(sporsmal, [{"tekst": "Ingen spesifikke fakta funnet i kunnskapsbasen.", "kilde": "System", "url": ""}])
            kilde_info = []
        
        return jsonify({
            "sporsmal": sporsmal,
            "svar": svar,
            "kilde": "faktabasert",
            "kilder": kilde_info,
            "brukte_lokal_kb": True
        })
    
    else:
        print("Generelt spørsmål - bruker GPT-4 fritt...")
        svar = generer_svar_generell(sporsmal)
        
        return jsonify({
            "sporsmal": sporsmal,
            "svar": svar,
            "kilde": "generell",
            "brukte_lokal_kb": False
        })

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "status": "OK",
        "modus": "Hybrid: Fakta for øyestyring, GPT-4 for generelt",
        "lokale_artikler": len(kunnskap)
    })

@app.route('/snakk', methods=['POST'])
def snakk_med_avatar():
    """
    Proxy for Heygen API - frontend spør oss, vi spør Heygen
    """
    data = request.get_json()
    tekst = data.get('tekst', '')
    
    if not tekst:
        return jsonify({"error": "Mangler tekst"}), 400
    
    try:
        # Vi bruker requests-biblioteket (må installeres: pip install requests)
        import requests
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {os.environ.get("HEYGEN_API_KEY", "HEYGEN_API_KEY")}'
            # Eller bytt ut med: 'Authorization': f'Bearer HEYGEN_API_KEY'
        }
        
        payload = {
            'avatar_id': data.get('avatar_id', 'AVATAR_ID'),
            'text': tekst[:1500],  # Begrrens lengde
            'voice_type': 'text'
        }
        
        response = requests.post(
            'https://api.heygen.com/v1/streaming.speak',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            return jsonify({"status": "ok", "melding": "Avataren snakker"})
        else:
            return jsonify({
                "status": "feil", 
                "melding": f"Heygen svarte: {response.status_code}",
                "detalj": response.text
            }), 500
            
    except Exception as e:
        return jsonify({"status": "feil", "melding": str(e)}), 500

# For produksjon (Render) - bruk miljøvariabler
import os
if os.environ.get('HEYGEN_API_KEY'):
    HEYGEN_API_KEY = os.environ.get('HEYGEN_API_KEY')
if os.environ.get('AVATAR_ID'):
    # Du må oppdatere koden din til å lese AVATAR_ID fra miljøvariabel også
    pass

if __name__ == '__main__':
    last_inn_kunnskap()
    # Bruk port fra miljøvariabel (Render setter denne) eller 5000 lokalt
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    last_inn_kunnskap()
    print("Smart server klar!")
    print("Husk: Bytt ut DIN_OPENAI_API_KEY_HER med din faktiske nøkkel!")
    print("Åpne: http://localhost:5000/")
    app.run(debug=True, port=5000)