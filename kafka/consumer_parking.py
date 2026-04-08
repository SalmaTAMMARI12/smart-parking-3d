"""
============================================================
 KAFKA CONSUMER — parking.capteurs → PostgreSQL
 
 Ce script tourne en dehors de Blender (terminal CMD).
 Il consomme les events Kafka et met à jour PostgreSQL.

 Lancement :
   python consumer_parking.py

 Il peut tourner en parallèle avec Blender.
============================================================
"""

import json
import signal
import sys
from datetime import datetime

try:
    import psycopg2
except ImportError:
    print("❌ pip install psycopg2-binary")
    sys.exit(1)

try:
    from kafka import KafkaConsumer
except ImportError:
    print("❌ pip install kafka-python")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────
KAFKA_BOOTSTRAP = "localhost:9092"
TOPIC_CAPTEURS  = "parking.capteurs"
GROUP_ID        = "consumer-postgresql"

PG_CONFIG = dict(
    host="localhost", port=5432,
    dbname="Parking", user="postgres", password="testpassword123"
)

# ── Connexion PostgreSQL ─────────────────────────────────────
conn = psycopg2.connect(**PG_CONFIG)
conn.autocommit = False
c = conn.cursor()
print(f"✅ PostgreSQL connecté : {PG_CONFIG['dbname']}")

# ── Consumer Kafka ───────────────────────────────────────────
consumer = KafkaConsumer(
    TOPIC_CAPTEURS,
    bootstrap_servers=KAFKA_BOOTSTRAP,
    group_id=GROUP_ID,
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='latest',   # lire depuis maintenant
    enable_auto_commit=True,
)
print(f"✅ Kafka Consumer connecté → topic={TOPIC_CAPTEURS}")
print(f"   Group ID : {GROUP_ID}")
print("\n🎧 En attente d'events...\n")

# ── Graceful shutdown ────────────────────────────────────────
running = True
def stop(sig, frame):
    global running
    print("\n⏹  Arrêt du consumer...")
    running = False

signal.signal(signal.SIGINT, stop)

# ── Boucle de consommation ───────────────────────────────────
total = 0
try:
    for message in consumer:
        if not running:
            break

        event = message.value
        place_id  = event.get("place_id")
        etat      = event.get("etat")
        timestamp = event.get("timestamp")
        source    = event.get("source", "?")

        try:
            ts = datetime.fromisoformat(timestamp)

            # Mise à jour table places
            c.execute(
                "UPDATE places SET etat=%s, timestamp=%s WHERE id=%s",
                (etat, ts, place_id)
            )
            # Insertion historique (pour IA prédictive phase 3)
            c.execute(
                "INSERT INTO historique (place_id, etat, timestamp) VALUES (%s,%s,%s)",
                (place_id, etat, ts)
            )
            conn.commit()

            total += 1
            emoji = "🔴" if etat == "occupee" else "🟢"
            print(f"  {emoji} [{total:04d}] {place_id} → {etat:8s}  "
                  f"{ts.strftime('%H:%M:%S.%f')[:12]}  "
                  f"offset={message.offset}")

        except Exception as e:
            conn.rollback()
            print(f"  ❌ Erreur traitement {place_id} : {e}")

except Exception as e:
    print(f"❌ Erreur consumer : {e}")
finally:
    consumer.close()
    conn.close()
    print(f"\n✅ Consumer arrêté — {total} events traités")