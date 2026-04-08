import bpy
import sys
import site
import json
from datetime import datetime

# ============================================================
#  SCRIPT 2 — DÉTECTION MULTI-VOITURES TEMPS RÉEL
# ============================================================

# ── Config ───────────────────────────────────────────────────
VOITURES        = ["Sketchfab_model", "Voiture_2"]  # ← liste des voitures
KAFKA_BOOTSTRAP = "localhost:9092"
TOPIC           = "parking.capteurs"
PG_HOST         = "localhost"
PG_PORT         = 5432
PG_DATABASE     = "Parking"
PG_USER         = "postgres"
PG_PASSWORD     = "testpassword123"

# ── Config parking ────────────────────────────────────────────
NB_LIGNES        = 5
PLACES_PAR_LIGNE = 14
LARGEUR_PLACE    = 2.5
LONGUEUR_PLACE   = 5.0
LARGEUR_VOIE     = 6.5
DEPTH            = 2.5
DEGAGEMENT_L1    = {5, 6, 7, 8}
OX = (PLACES_PAR_LIGNE * LARGEUR_PLACE) / 2
OY = (NB_LIGNES * (LONGUEUR_PLACE + LARGEUR_VOIE)) / 2
ZP = -DEPTH

# ── Imports ───────────────────────────────────────────────────
for p in [r"C:\blender_libs", site.getusersitepackages()]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from kafka import KafkaProducer
    from kafka.errors import KafkaError
    KAFKA_OK = True
    print("✅ kafka-python OK")
except ImportError:
    KAFKA_OK = False
    print("❌ kafka-python manquant")

try:
    import psycopg2
    PG_OK = True
    print("✅ psycopg2 OK")
except ImportError:
    PG_OK = False
    print("❌ psycopg2 manquant")

# ── Kafka Producer singleton ──────────────────────────────────
_producer = [None]

def get_producer():
    if _producer[0] is not None:
        return _producer[0]
    if not KAFKA_OK:
        return None
    try:
        p = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',
            retries=3,
            request_timeout_ms=5000,
        )
        _producer[0] = p
        print(f"✅ Kafka Producer connecté → {KAFKA_BOOTSTRAP}")
        return p
    except Exception as e:
        print(f"❌ Kafka erreur : {e}")
        return None

# ── Bounds des places ─────────────────────────────────────────
def build_bounds():
    bounds = {}
    for l in range(NB_LIGNES):
        row_y = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE/2
        for p in range(PLACES_PAR_LIGNE):
            if l == 0 and p in DEGAGEMENT_L1:
                continue
            pid = f"L{l+1:02d}P{p+1:02d}"
            px  = (p+0.5)*LARGEUR_PLACE - OX
            bounds[pid] = {
                'x_min': px - LARGEUR_PLACE/2,
                'x_max': px + LARGEUR_PLACE/2,
                'y_min': row_y - LONGUEUR_PLACE/2,
                'y_max': row_y + LONGUEUR_PLACE/2,
            }
    return bounds

PLACES_BOUNDS = build_bounds()

# ── État par voiture ──────────────────────────────────────────
_states = {nom: {'place_precedente': None} for nom in VOITURES}

# ── Changer couleur dans Blender ──────────────────────────────
def changer_couleur(place_id, etat):
    place_obj   = bpy.data.objects.get(f"Place_{place_id}")
    capteur_obj = bpy.data.objects.get(f"Capteur_{place_id}")
    nom_p = "Place_Occupee"   if etat == 'occupee' else "Place_Libre"
    nom_c = "Capteur_Occupee" if etat == 'occupee' else "Capteur_Libre"
    if place_obj and place_obj.data.materials:
        m = bpy.data.materials.get(nom_p)
        if m: place_obj.data.materials[0] = m
    if capteur_obj and capteur_obj.data.materials:
        m = bpy.data.materials.get(nom_c)
        if m: capteur_obj.data.materials[0] = m

# ── Envoyer event Kafka ───────────────────────────────────────
def envoyer_kafka(place_id, etat, x, y, nom_voiture):
    producer = get_producer()
    if producer is None:
        return False
    try:
        event = {
            "place_id":   place_id,
            "etat":       etat,
            "timestamp":  datetime.now().isoformat(),
            "capteur_id": f"CAP_{place_id}",
            "voiture":    nom_voiture,
            "position":   {"x": round(x,3), "y": round(y,3)},
            "source":     "blender_simulation"
        }
        producer.send(TOPIC, key=place_id.encode(), value=event)
        producer.flush(timeout=1)
        emoji = "🔴" if etat == "occupee" else "🟢"
        print(f"  {emoji} Kafka : {place_id} → {etat} ({nom_voiture})")
        return True
    except Exception as e:
        print(f"  ❌ Kafka erreur : {e}")
        return False

# ── Mettre à jour PostgreSQL ──────────────────────────────────
def maj_postgres(place_id, etat):
    if not PG_OK:
        return
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT,
            dbname=PG_DATABASE, user=PG_USER, password=PG_PASSWORD
        )
        c   = conn.cursor()
        now = datetime.now()
        c.execute("UPDATE places SET etat=%s, timestamp=%s WHERE id=%s", (etat, now, place_id))
        c.execute("INSERT INTO historique (place_id, etat, timestamp) VALUES (%s,%s,%s)", (place_id, etat, now))
        conn.commit()
        conn.close()
        print(f"  ✅ PostgreSQL : {place_id} → {etat}")
    except Exception as e:
        print(f"  ❌ PostgreSQL erreur : {e}")

# ── Handler principal — boucle sur toutes les voitures ────────
def detecter_voiture(scene):
    for nom_voiture in VOITURES:                          # ← boucle sur la liste
        voiture = bpy.data.objects.get(nom_voiture)       # ← string unique ici
        if voiture is None:
            continue

        x = voiture.location.x
        y = voiture.location.y

        place_actuelle = None
        for pid, b in PLACES_BOUNDS.items():
            if b['x_min'] <= x <= b['x_max'] and b['y_min'] <= y <= b['y_max']:
                place_actuelle = pid
                break

        place_precedente = _states[nom_voiture]['place_precedente']

        if place_actuelle != place_precedente:
            if place_precedente:
                changer_couleur(place_precedente, 'libre')
                if not envoyer_kafka(place_precedente, 'libre', x, y, nom_voiture):
                    maj_postgres(place_precedente, 'libre')
                print(f"  🟢 Libéré : {place_precedente} ({nom_voiture})")

            if place_actuelle:
                changer_couleur(place_actuelle, 'occupee')
                if not envoyer_kafka(place_actuelle, 'occupee', x, y, nom_voiture):
                    maj_postgres(place_actuelle, 'occupee')
                print(f"  🔴 Occupé : {place_actuelle} ({nom_voiture})")

            _states[nom_voiture]['place_precedente'] = place_actuelle

# ── Enregistrer le handler ────────────────────────────────────
for h in list(bpy.app.handlers.depsgraph_update_post):
    if getattr(h, '__name__', '') == 'detecter_voiture':
        bpy.app.handlers.depsgraph_update_post.remove(h)

bpy.app.handlers.depsgraph_update_post.append(detecter_voiture)

# ── Résumé ────────────────────────────────────────────────────
print("\n" + "="*50)
print("  🚗 DÉTECTION MULTI-VOITURES ACTIVE")
print("="*50)
for nom in VOITURES:
    v = bpy.data.objects.get(nom)
    if v:
        print(f"  ✅ {nom} : X={v.location.x:.2f} Y={v.location.y:.2f}")
    else:
        print(f"  ❌ {nom} introuvable !")
print(f"  {'✅' if KAFKA_OK else '❌'} Kafka   : {KAFKA_BOOTSTRAP}")
print(f"  {'✅' if PG_OK   else '❌'} Postgres: {PG_HOST}/{PG_DATABASE}")
print(f"  📍 {len(PLACES_BOUNDS)} places surveillées")
print("="*50)
print("\n  POUR TESTER :")
print("  v1 = bpy.data.objects.get('Sketchfab_model')")
print("  v1.location.x = -6.25")
print("  v1.location.y = -26.25")
print("  v2 = bpy.data.objects.get('Voiture_2')")
print("  v2.location.x = -13.75")
print("  v2.location.y = -26.25")
print("="*50 + "\n")