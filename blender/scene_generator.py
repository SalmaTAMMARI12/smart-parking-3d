import bpy
import math
import random
import sys
import os
from datetime import datetime

# ============================================================
#  UNDERGROUND PARKING — Version 5.0
#  + PostgreSQL + Capteurs simulés + Couleurs temps réel
# ============================================================

# ============================================================
#  CONNEXION POSTGRESQL
#  ⚠️ Modifier uniquement ces 3 lignes si besoin
# ============================================================
PG_HOST     = "localhost"
PG_PORT     = 5432
PG_DATABASE = "Parking"
PG_USER     = "postgres"
PG_PASSWORD = "testpassword123"   # ← ton mot de passe PostgreSQL

# ============================================================
#  Import psycopg2 — cherche dans le Python de Blender
# ============================================================
try:
    import psycopg2
    import psycopg2.extras
    print("✅ psycopg2 importé avec succès")
except ImportError:
    # Ajouter le chemin user-site de Blender
    import site
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    try:
        import psycopg2
        import psycopg2.extras
        print("✅ psycopg2 trouvé dans user-site")
    except ImportError:
        print("❌ ERREUR : psycopg2 non trouvé !")
        print("   Lance cette commande dans CMD puis relance Blender :")
        print('   "C:\\Program Files\\Blender Foundation\\Blender 5.0\\5.0\\python\\bin\\python.exe" -m pip install psycopg2-binary')
        raise

# ============================================================
#  FONCTION CONNEXION
# ============================================================
def get_conn():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        dbname=PG_DATABASE, user=PG_USER, password=PG_PASSWORD
    )

# ============================================================
#  INITIALISATION BASE DE DONNÉES
# ============================================================
DEGAGEMENT_L1 = {5, 6, 7, 8}  # places 6-7-8-9 de L1 = zone entrée voitures

def init_database(nb_lignes, places_par_ligne):
    """Crée les tables si elles n'existent pas et insère les places."""
    conn = get_conn()
    c    = conn.cursor()

    # ── Création des tables ──────────────────────────────────
    c.execute('''
        CREATE TABLE IF NOT EXISTS places (
            id          VARCHAR(10) PRIMARY KEY,
            ligne       INTEGER,
            colonne     INTEGER,
            etat        VARCHAR(10) DEFAULT 'libre',
            capteur_id  VARCHAR(15),
            timestamp   TIMESTAMP,
            type_place  VARCHAR(15) DEFAULT 'standard'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS capteurs (
            capteur_id       VARCHAR(15) PRIMARY KEY,
            place_id         VARCHAR(10),
            actif            BOOLEAN DEFAULT TRUE,
            derniere_lecture TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS historique (
            id        SERIAL PRIMARY KEY,
            place_id  VARCHAR(10),
            etat      VARCHAR(10),
            timestamp TIMESTAMP
        )
    ''')

    # ── Insertion des places (seulement si table vide) ───────
    c.execute("SELECT COUNT(*) FROM places")
    if c.fetchone()[0] == 0:
        now = datetime.now()
        for l in range(nb_lignes):
            for p in range(places_par_ligne):
                if l == 0 and p in DEGAGEMENT_L1:
                    continue
                place_id   = f"L{l+1:02d}P{p+1:02d}"
                capteur_id = f"CAP_{place_id}"
                type_place = (
                    "handicap"   if p == 0 else
                    "electrique" if p == places_par_ligne - 1 else
                    "standard"
                )
                c.execute(
                    "INSERT INTO places VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (place_id, l+1, p+1, 'libre', capteur_id, now, type_place)
                )
                c.execute(
                    "INSERT INTO capteurs VALUES (%s,%s,%s,%s)",
                    (capteur_id, place_id, True, now)
                )
        nb_places = nb_lignes * places_par_ligne - len(DEGAGEMENT_L1)
        conn.commit()
        print(f"✅ PostgreSQL : {nb_places} places insérées (4 zone dégagement exclues)")
    else:
        c.execute("SELECT COUNT(*) FROM places")
        n = c.fetchone()[0]
        print(f"✅ PostgreSQL : BDD existante — {n} places chargées")

    conn.close()

# ============================================================
#  SIMULATION CAPTEURS → mise à jour PostgreSQL
# ============================================================
def simuler_capteurs(nb_lignes, places_par_ligne, taux_occupation=0.60):
    """Simule les capteurs IR et met à jour PostgreSQL en temps réel."""
    conn = get_conn()
    c    = conn.cursor()
    now  = datetime.now()

    etats = {}
    for l in range(nb_lignes):
        for p in range(places_par_ligne):
            if l == 0 and p in DEGAGEMENT_L1:
                continue
            place_id = f"L{l+1:02d}P{p+1:02d}"
            # Capteur IR : 1 = voiture détectée, 0 = libre
            etat = 'occupee' if random.random() < taux_occupation else 'libre'
            etats[place_id] = etat

            # Mise à jour table places
            c.execute(
                "UPDATE places SET etat=%s, timestamp=%s WHERE id=%s",
                (etat, now, place_id)
            )
            # Mise à jour table capteurs
            c.execute(
                "UPDATE capteurs SET derniere_lecture=%s WHERE place_id=%s",
                (now, place_id)
            )
            # Ajout dans historique (pour future IA prédictive)
            c.execute(
                "INSERT INTO historique (place_id, etat, timestamp) VALUES (%s,%s,%s)",
                (place_id, etat, now)
            )

    conn.commit()

    # Stats console
    total    = nb_lignes * places_par_ligne - len(DEGAGEMENT_L1)
    occupees = sum(1 for v in etats.values() if v == 'occupee')
    libres   = total - occupees
    print(f"\n📡 Capteurs simulés → {occupees}/{total} ({occupees/total*100:.0f}% occupées)")
    print(f"   🟢 Libres : {libres}   🔴 Occupées : {occupees}")
    print(f"   ⛔ Zone entrée : L1P06→P09 exclues (passage voitures)")

    conn.close()
    return etats

# ============================================================
#  LECTURE ÉTATS DEPUIS POSTGRESQL
# ============================================================
def lire_etats_pg():
    """Lit tous les états depuis PostgreSQL."""
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT id, etat FROM places")
    etats = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return etats

def stats_parking():
    """Stats globales depuis PostgreSQL."""
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM places")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM places WHERE etat='occupee'")
    occupees = c.fetchone()[0]
    conn.close()
    return {
        "total": total, "occupees": occupees,
        "libres": total - occupees,
        "taux": occupees / total * 100 if total > 0 else 0
    }

# ============================================================
#  NETTOYAGE SCÈNE BLENDER
# ============================================================
def cleanup():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for blk in [bpy.data.materials, bpy.data.meshes,
                bpy.data.lights, bpy.data.cameras, bpy.data.curves]:
        for item in list(blk):
            blk.remove(item)

cleanup()

# ============================================================
#  CONFIG PARKING
# ============================================================
NB_LIGNES        = 5
PLACES_PAR_LIGNE = 14
LARGEUR_PLACE    = 2.5
LONGUEUR_PLACE   = 5.0
LARGEUR_VOIE     = 6.5
HAUTEUR_PLAFOND  = 2.8
EPAISSEUR_DALLE  = 0.3
DEPTH            = 2.5
ramp_w           = 8.0
ramp_len         = 12.0

TOTAL_W = PLACES_PAR_LIGNE * LARGEUR_PLACE
TOTAL_D = NB_LIGNES * (LONGUEUR_PLACE + LARGEUR_VOIE)
OX, OY  = TOTAL_W / 2, TOTAL_D / 2
ZP      = -DEPTH

# ============================================================
#  INIT BDD + SIMULATION CAPTEURS
# ============================================================
print("\n🔌 Connexion à PostgreSQL...")
init_database(NB_LIGNES, PLACES_PAR_LIGNE)
ETATS_PLACES = simuler_capteurs(NB_LIGNES, PLACES_PAR_LIGNE, taux_occupation=0.60)

# ============================================================
#  COLLECTIONS
# ============================================================
def get_col(name):
    if name not in bpy.data.collections:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return bpy.data.collections[name]

COLS = {n: get_col(n) for n in [
    "Structure","Piliers","Lumieres","Marquage",
    "Technique","Signalétique","Barrières","Sécurité","Places"
]}

def link_to(obj, col_name):
    dest = COLS[col_name]
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    dest.objects.link(obj)

# ============================================================
#  HELPER LUMIÈRE
# ============================================================
def add_light(light_type, loc, energy, color=(1,1,1), rot=(math.pi,0,0),
              size=1.0, size_y=None, spot_size=math.radians(45)):
    bpy.ops.object.light_add(type=light_type, location=loc)
    l = bpy.context.object
    l.data.energy = energy
    l.data.color  = color
    l.rotation_euler = rot
    if light_type == 'AREA':
        l.data.size   = size
        l.data.size_y = size_y if size_y else size
    elif light_type == 'SPOT':
        l.data.spot_size  = spot_size
        l.data.spot_blend = 0.3
    link_to(l, "Lumieres")
    return l

# ============================================================
#  MATÉRIAUX
# ============================================================
def mat(name, color, roughness=0.5, metallic=0.0,
        em_color=None, em_strength=0.0, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    p   = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(p.outputs['BSDF'], out.inputs['Surface'])
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value  = roughness
    p.inputs['Metallic'].default_value   = metallic
    if alpha < 1.0:
        p.inputs['Alpha'].default_value = alpha
        m.blend_method = 'BLEND'
    if em_strength > 0:
        ec = em_color if em_color else color
        if 'Emission Color' in p.inputs:
            p.inputs['Emission Color'].default_value    = (*ec, 1)
            p.inputs['Emission Strength'].default_value = em_strength
    return m

M = {
    'sol'             : mat("Sol",              (0.06,0.06,0.06), roughness=0.2),
    'dalle'           : mat("Dalle",            (0.18,0.18,0.18), roughness=0.85),
    'beton'           : mat("Beton",            (0.22,0.22,0.22), roughness=0.9),
    'jaune'           : mat("Jaune",            (1.0,0.55,0.0),   roughness=0.4),
    'blanc'           : mat("Blanc",            (0.9,0.9,0.9),    roughness=0.4),
    'rouge'           : mat("Rouge",            (0.8,0.05,0.05),  roughness=0.4),
    'vert'            : mat("Vert",             (0.05,0.7,0.1),   roughness=0.4),
    'bleu'            : mat("Bleu",             (0.05,0.15,0.85), roughness=0.4),
    'noir'            : mat("Noir",             (0.02,0.02,0.02), roughness=0.6),
    'metal'           : mat("Metal",            (0.55,0.55,0.55), roughness=0.25, metallic=0.9),
    'metal_dark'      : mat("Metal_Dark",       (0.12,0.12,0.12), roughness=0.4,  metallic=0.8),
    'neon_blanc'      : mat("Neon_Blanc",       (0.95,0.97,1.0),  em_strength=12),
    'neon_jaune'      : mat("Neon_Jaune",       (1.0,0.75,0.0),   em_strength=8),
    'neon_rouge'      : mat("Neon_Rouge",       (1.0,0.1,0.1),    em_strength=8),
    'neon_vert'       : mat("Neon_Vert",        (0.1,1.0,0.2),    em_strength=8),
    'p_blanc'         : mat("Paint_Blanc",      (0.95,0.95,0.95), roughness=0.2),
    'p_jaune'         : mat("Paint_Jaune",      (1.0,0.7,0.0),    roughness=0.2),
    'asphalt'         : mat("Asphalt",          (0.08,0.08,0.08), roughness=0.95),
    'place_libre'     : mat("Place_Libre",      (0.04,0.65,0.12), roughness=0.35, em_strength=2.5, em_color=(0.04,0.65,0.12)),
    'place_occupee'   : mat("Place_Occupee",    (0.75,0.04,0.04), roughness=0.35, em_strength=2.5, em_color=(0.75,0.04,0.04)),
    'place_handicap'  : mat("Place_Handicap",   (0.05,0.15,0.85), roughness=0.35, em_strength=1.5, em_color=(0.05,0.15,0.85)),
    'place_electrique': mat("Place_Electrique", (0.55,0.0,0.85),  roughness=0.35, em_strength=1.5, em_color=(0.55,0.0,0.85)),
    'capteur_libre'   : mat("Capteur_Libre",    (0.0,1.0,0.2),    em_strength=15),
    'capteur_occupee' : mat("Capteur_Occupee",  (1.0,0.05,0.05),  em_strength=15),
}

# ============================================================
#  HELPERS MESH
# ============================================================
def box(loc, sc, mat_key, col):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.scale = sc
    o.data.materials.append(M[mat_key])
    link_to(o, col)
    return o

def cyl(loc, r, depth, mat_key, col, rot=(0,0,0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc)
    o = bpy.context.object
    o.rotation_euler = rot
    o.data.materials.append(M[mat_key])
    link_to(o, col)
    return o

def get_place_mat(place_id, etat):
    """Retourne les matériaux selon l'état et le type de place."""
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT type_place FROM places WHERE id=%s", (place_id,))
    row  = c.fetchone()
    conn.close()
    type_place = row[0] if row else 'standard'
    if etat == 'occupee':
        return 'place_occupee', 'capteur_occupee'
    elif type_place == 'handicap':
        return 'place_handicap', 'capteur_libre'
    elif type_place == 'electrique':
        return 'place_electrique', 'capteur_libre'
    else:
        return 'place_libre', 'capteur_libre'

# ============================================================
#  STRUCTURE
# ============================================================
box((0, 0, ZP-EPAISSEUR_DALLE/2), (TOTAL_W/2+8, TOTAL_D/2+8, EPAISSEUR_DALLE/2), 'asphalt', "Structure")
box((0, 0, ZP+HAUTEUR_PLAFOND+EPAISSEUR_DALLE/2), (TOTAL_W/2+8, TOTAL_D/2+8, EPAISSEUR_DALLE/2), 'dalle', "Structure")
box(( TOTAL_W/2+8, 0, ZP+HAUTEUR_PLAFOND/2), (0.3, TOTAL_D/2+8, HAUTEUR_PLAFOND/2), 'beton', "Structure")
box((-TOTAL_W/2-8, 0, ZP+HAUTEUR_PLAFOND/2), (0.3, TOTAL_D/2+8, HAUTEUR_PLAFOND/2), 'beton', "Structure")
box((0,  TOTAL_D/2+8, ZP+HAUTEUR_PLAFOND/2), (TOTAL_W/2+8, 0.3, HAUTEUR_PLAFOND/2), 'beton', "Structure")
box((0, -TOTAL_D/2-8, ZP+HAUTEUR_PLAFOND/2), (TOTAL_W/2+8, 0.3, HAUTEUR_PLAFOND/2), 'beton', "Structure")

# ============================================================
#  PILIERS
# ============================================================
def make_pillar(x, y):
    box((x, y, ZP+HAUTEUR_PLAFOND/2), (0.28, 0.28, HAUTEUR_PLAFOND/2), 'beton', "Piliers")
    box((x, y, ZP+0.45), (0.31, 0.31, 0.45), 'jaune', "Piliers")
    for i in range(5):
        box((x, y, ZP+0.1+i*0.18), (0.32, 0.32, 0.05), 'noir', "Piliers")
    box((x, y, ZP+HAUTEUR_PLAFOND-0.04), (0.32, 0.32, 0.04), 'beton', "Piliers")

for l in range(NB_LIGNES):
    row_y = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE/2
    py    = row_y + LONGUEUR_PLACE/2 + 0.3
    step  = LARGEUR_PLACE * 3
    x     = -OX + step/2
    while x < OX:
        make_pillar(x, py)
        x += step

# ============================================================
#  RANGÉES : MARQUAGE + PLACES COLORÉES DEPUIS POSTGRESQL
# ============================================================
for l in range(NB_LIGNES):
    row_y  = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE/2
    voie_y = row_y + LONGUEUR_PLACE/2 + LARGEUR_VOIE/2

    # Lignes de délimitation blanches
    for p in range(PLACES_PAR_LIGNE + 1):
        rx = p*LARGEUR_PLACE - OX
        box((rx, row_y, ZP+0.003), (0.04, LONGUEUR_PLACE/2, 0.003), 'p_blanc', "Marquage")
    box((0, row_y-LONGUEUR_PLACE/2, ZP+0.003), (TOTAL_W/2, 0.05, 0.003), 'p_blanc', "Marquage")

    # Tirets jaunes voie
    for dash in range(int(TOTAL_W / 2)):
        dx = -TOTAL_W/2 + dash*2 + 0.5
        box((dx, voie_y, ZP+0.003), (0.45, 0.06, 0.002), 'p_jaune', "Marquage")

    # Flèches directionnelles
    for ax in [-OX+4, 0, OX-4]:
        box((ax, voie_y, ZP+0.004),       (0.12, 0.5, 0.002), 'p_blanc', "Marquage")
        box((ax-0.18, voie_y-0.4, ZP+0.004), (0.07, 0.07, 0.002), 'p_blanc', "Marquage")
        box((ax+0.18, voie_y-0.4, ZP+0.004), (0.07, 0.07, 0.002), 'p_blanc', "Marquage")

    # ── ZONE DÉGAGEMENT ENTRÉE (L1, places 6-9) ──────────────
    if l == 0:
        dz_w = 4 * LARGEUR_PLACE
        dz_x = (5 + 0.5 + 1.5) * LARGEUR_PLACE - OX
        box((dz_x, row_y, ZP+0.004), (dz_w/2-0.05, LONGUEUR_PLACE/2-0.05, 0.004), 'asphalt', "Marquage")
        for ci in range(5, 9):
            cx = (ci+0.5)*LARGEUR_PLACE - OX
            for sign in [-1, 1]:
                bpy.ops.mesh.primitive_cube_add(location=(cx+sign*0.5, row_y, ZP+0.006))
                chv = bpy.context.object
                chv.scale = (0.06, 0.8, 0.002)
                chv.rotation_euler = (0, 0, math.radians(45*sign))
                chv.data.materials.append(M['p_jaune'])
                link_to(chv, "Marquage")
        box((dz_x, row_y+0.6, ZP+0.007),    (0.12, 0.7, 0.002), 'p_blanc', "Marquage")
        box((dz_x-0.28, row_y-0.2, ZP+0.007),(0.08, 0.08, 0.002),'p_blanc', "Marquage")
        box((dz_x+0.28, row_y-0.2, ZP+0.007),(0.08, 0.08, 0.002),'p_blanc', "Marquage")
        box((dz_x, row_y-LONGUEUR_PLACE/2+0.15, ZP+0.006),(dz_w/2-0.1, 0.08, 0.002),'bleu',"Marquage")

    # ── PLACES COLORÉES DEPUIS POSTGRESQL ────────────────────
    for p in range(PLACES_PAR_LIGNE):
        if l == 0 and p in DEGAGEMENT_L1:
            continue

        place_id = f"L{l+1:02d}P{p+1:02d}"
        etat     = ETATS_PLACES.get(place_id, 'libre')
        px       = (p + 0.5) * LARGEUR_PLACE - OX
        py_place = row_y

        mat_place, mat_cap = get_place_mat(place_id, etat)

        # Sol coloré de la place
        bpy.ops.mesh.primitive_cube_add(location=(px, py_place, ZP+0.005))
        sol_place = bpy.context.object
        sol_place.scale = (LARGEUR_PLACE/2-0.08, LONGUEUR_PLACE/2-0.08, 0.005)
        sol_place.data.materials.append(M[mat_place])
        sol_place.name = f"Place_{place_id}"
        link_to(sol_place, "Places")

        # Poteau capteur IR
        cyl((px, py_place-LONGUEUR_PLACE/2+0.2, ZP+0.5), 0.03, 1.0, 'metal_dark', "Places")

        # LED indicatrice (sphère émissive)
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.07,
            location=(px, py_place-LONGUEUR_PLACE/2+0.2, ZP+1.08))
        led = bpy.context.object
        led.data.materials.append(M[mat_cap])
        led.name = f"Capteur_{place_id}"
        link_to(led, "Places")

        # Plaque numéro
        box((px, py_place-LONGUEUR_PLACE/2+0.22, ZP+0.82), (0.15, 0.01, 0.06), 'metal_dark', "Places")

# ============================================================
#  NÉONS PLAFOND
# ============================================================
for l in range(NB_LIGNES):
    row_y  = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE/2
    voie_y = row_y + LONGUEUR_PLACE/2 + LARGEUR_VOIE/2
    for nx in range(int(-TOTAL_W/2)+2, int(TOTAL_W/2)-1, 4):
        box((nx, voie_y, ZP+HAUTEUR_PLAFOND-0.06), (1.65, 0.07, 0.04), 'metal_dark', "Lumieres")
        box((nx, voie_y, ZP+HAUTEUR_PLAFOND-0.09), (1.60, 0.04, 0.02), 'neon_blanc', "Lumieres")
    add_light('AREA', (0, voie_y, ZP+HAUTEUR_PLAFOND-0.1),
              energy=400, color=(0.9,0.95,1.0), rot=(math.pi,0,0),
              size=TOTAL_W, size_y=2.0)

# ============================================================
#  TUYAUTERIES PLAFOND
# ============================================================
for l in range(NB_LIGNES):
    row_y  = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE/2
    voie_y = row_y + LONGUEUR_PLACE/2 + LARGEUR_VOIE/2
    box((0, voie_y, ZP+HAUTEUR_PLAFOND-0.22), (TOTAL_W/2, 0.22, 0.13), 'metal', "Technique")
    for xd in range(int(-TOTAL_W/2)+2, int(TOTAL_W/2)-1, 3):
        cyl((xd, voie_y, ZP+HAUTEUR_PLAFOND-0.36), 0.16, 0.05, 'metal_dark', "Technique")
        cyl((xd, voie_y, ZP+HAUTEUR_PLAFOND-0.39), 0.11, 0.02, 'noir', "Technique")
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.03, depth=TOTAL_W,
        location=(0, row_y+LONGUEUR_PLACE/2+0.5, ZP+HAUTEUR_PLAFOND-0.12))
    t = bpy.context.object
    t.rotation_euler = (0, math.pi/2, 0)
    t.data.materials.append(M['rouge'])
    link_to(t, "Technique")
    box((-OX-0.04, row_y, ZP+1.2), (0.04, 0.18, 0.28), 'metal_dark', "Technique")
    box((-OX-0.05, row_y, ZP+1.2), (0.01, 0.16, 0.26), 'jaune', "Technique")

# ============================================================
#  RAMPE
# ============================================================
N_STEPS   = 20
step_len  = ramp_len / N_STEPS
step_drop = DEPTH   / N_STEPS

for i in range(N_STEPS):
    seg_y = -OY - i*step_len - step_len/2
    seg_z = -i*step_drop - step_drop/2 - DEPTH
    bpy.ops.mesh.primitive_cube_add(location=(0, seg_y, seg_z))
    seg = bpy.context.object
    seg.scale = (ramp_w/2, step_len/2+0.02, 0.15)
    seg.rotation_euler = (math.atan2(step_drop, step_len), 0, 0)
    seg.data.materials.append(M['asphalt'])
    link_to(seg, "Structure")

for side in [-1, 1]:
    for i in range(N_STEPS):
        seg_y  = -OY - i*step_len - step_len/2
        seg_z  = -i*step_drop - step_drop - DEPTH
        wall_h = DEPTH - i*step_drop + 0.5
        bpy.ops.mesh.primitive_cube_add(
            location=(side*(ramp_w/2+0.2), seg_y, seg_z+wall_h/2))
        mur = bpy.context.object
        mur.scale = (0.2, step_len/2+0.02, wall_h/2)
        mur.data.materials.append(M['beton'])
        link_to(mur, "Structure")
    box((side*(ramp_w/2+0.2), -OY-ramp_len/2, -DEPTH/2),
        (0.22, ramp_len/2, 0.06), 'jaune', "Structure")

for i in range(N_STEPS):
    seg_y = -OY - i*step_len - step_len/2
    seg_z = -i*step_drop - step_drop/2 - DEPTH + 0.16
    bpy.ops.mesh.primitive_cube_add(location=(0, seg_y, seg_z))
    ln = bpy.context.object
    ln.scale = (0.06, step_len/2, 0.01)
    ln.rotation_euler = (math.atan2(step_drop, step_len), 0, 0)
    ln.data.materials.append(M['p_jaune'])
    link_to(ln, "Marquage")

box((0, -OY-ramp_len/2, 0.15), (ramp_w/2+0.5, ramp_len/2, 0.15), 'dalle', "Structure")

for i in range(5):
    t  = i/4.0
    ly = -OY - t*ramp_len
    lz = -t*DEPTH - DEPTH + 1.0
    add_light('POINT', (0, ly, lz), energy=200, color=(1.0,0.88,0.65), rot=(0,0,0))

# ============================================================
#  BARRIÈRES
# ============================================================
BY = -OY - ramp_len - 0.5
BZ = ZP

def make_barrier(x, y, z, is_entry=True):
    cm  = 'neon_vert'   if is_entry else 'neon_rouge'
    sm  = 'vert'        if is_entry else 'rouge'
    col = (0.2,1.0,0.2) if is_entry else (1.0,0.2,0.2)
    box((x, y, z+0.7),        (0.18, 0.11, 0.7),    'metal_dark', "Barrières")
    box((x, y+0.12, z+0.7),   (0.16, 0.01, 0.68),   'metal',      "Barrières")
    box((x, y+0.13, z+0.95),  (0.09, 0.005, 0.1),   cm,           "Barrières")
    cyl((x, y+0.13, z+0.7),   0.022, 0.01, sm, "Barrières", rot=(math.pi/2,0,0))
    box((x, y+0.13, z+0.55),  (0.05, 0.005, 0.035), 'noir',       "Barrières")
    cyl((x, y, z+0.6), 0.05, 1.2, 'metal', "Barrières")
    arm_len = 3.2
    box((x+arm_len/2, y, z+1.25), (arm_len/2, 0.04, 0.04), 'jaune', "Barrières")
    for i in range(6):
        bx = x + (i+0.5)/6*arm_len
        box((bx, y, z+1.25), (0.1, 0.045, 0.045), 'noir', "Barrières")
    cyl((x+arm_len, y, z+1.25), 0.045, 0.06, 'neon_rouge', "Barrières")
    box((x, y, z+2.4),     (0.55, 0.05, 0.18), sm, "Signalétique")
    box((x, y+0.06, z+2.4),(0.52, 0.002, 0.15), cm, "Signalétique")
    add_light('SPOT', (x, y+1, z+2.5), energy=600, color=col,
              rot=(math.pi,0,0), spot_size=math.radians(50))

make_barrier(-ramp_w/4, BY, BZ, is_entry=True)
make_barrier( ramp_w/4, BY, BZ, is_entry=False)
box((0, BY, BZ+0.6),  (0.2, 0.5, 0.6),  'beton', "Structure")
box((0, BY, BZ+1.25), (0.2, 0.5, 0.06), 'jaune', "Structure")

# ============================================================
#  PORTE D'ENTRÉE
# ============================================================
PY = -OY
PW = ramp_w
for side in [-1, 1]:
    box((side*PW/2, PY, ZP+HAUTEUR_PLAFOND/2), (0.2, 0.2, HAUTEUR_PLAFOND/2), 'metal_dark', "Structure")
    for i in range(4):
        box((side*PW/2, PY, ZP+0.2+i*0.5), (0.22, 0.22, 0.08), 'jaune', "Structure")
box((0, PY, ZP+HAUTEUR_PLAFOND-0.15), (PW/2, 0.2, 0.2), 'metal_dark', "Structure")
box((0, PY-0.22, ZP+HAUTEUR_PLAFOND-0.15), (PW/2-0.3,  0.02,  0.18), 'bleu', "Signalétique")
box((0, PY-0.24, ZP+HAUTEUR_PLAFOND-0.15), (PW/2-0.35, 0.005, 0.14), 'neon_blanc', "Signalétique")
box((-PW/2+1.2, PY-0.22, ZP+HAUTEUR_PLAFOND-0.5), (0.3, 0.02, 0.2),   'rouge',     "Signalétique")
box((-PW/2+1.2, PY-0.24, ZP+HAUTEUR_PLAFOND-0.5), (0.25,0.005,0.16),  'neon_rouge',"Signalétique")
for side in [-1, 1]:
    fx = side*PW/4
    box((fx, PY-0.15, ZP+HAUTEUR_PLAFOND-0.4),  (0.1,  0.06,  0.18), 'noir',      "Signalétique")
    cyl((fx, PY-0.22, ZP+HAUTEUR_PLAFOND-0.35), 0.07, 0.02, 'neon_vert', "Signalétique", rot=(math.pi/2,0,0))
    cyl((fx, PY-0.22, ZP+HAUTEUR_PLAFOND-0.5),  0.07, 0.02, 'rouge',     "Signalétique", rot=(math.pi/2,0,0))
box((0, PY+0.3, ZP+0.003), (PW/2, 0.15, 0.002), 'p_jaune', "Marquage")
box((0, PY-0.3, ZP+0.003), (PW/2, 0.15, 0.002), 'p_jaune', "Marquage")
add_light('SPOT', (0, PY+2, ZP+HAUTEUR_PLAFOND-0.1), energy=800, color=(0.9,0.95,1.0),
          rot=(math.pi,0,0), spot_size=math.radians(60))

# ============================================================
#  PANNEAU TABLEAU DE BORD (stats depuis PostgreSQL)
# ============================================================
stats = stats_parking()
box((0, PY-0.5, ZP+HAUTEUR_PLAFOND+0.6),   (2.5,  0.08, 0.5),  'metal_dark', "Signalétique")
box((-0.8, PY-0.59, ZP+HAUTEUR_PLAFOND+0.7),(0.65, 0.02, 0.12), 'neon_vert',  "Signalétique")
box(( 0.8, PY-0.59, ZP+HAUTEUR_PLAFOND+0.7),(0.65, 0.02, 0.12), 'neon_rouge', "Signalétique")
box((0,    PY-0.59, ZP+HAUTEUR_PLAFOND+0.6),(0.02, 0.02, 0.45), 'jaune',      "Signalétique")

# ============================================================
#  CAMÉRAS DE SÉCURITÉ
# ============================================================
def make_security_cam(x, y, z, az=0):
    box((x, y, z), (0.07, 0.12, 0.06), 'metal_dark', "Sécurité")
    bpy.context.object.rotation_euler = (math.radians(25), 0, az)
    cyl((x, y, z+0.12), 0.025, 0.22, 'metal_dark', "Sécurité")
    cyl((x+math.sin(az)*0.1, y+math.cos(az)*0.1, z-0.01),
        0.025, 0.05, 'noir', "Sécurité", rot=(math.radians(25),0,az))
    cyl((x, y, z+0.07), 0.007, 0.009, 'neon_rouge', "Sécurité")

cam_pts = [
    (-OX+0.8, -OY+0.8, ZP+HAUTEUR_PLAFOND-0.18, math.radians(45)),
    ( OX-0.8, -OY+0.8, ZP+HAUTEUR_PLAFOND-0.18, math.radians(-45)),
    (-OX+0.8,  OY-0.8, ZP+HAUTEUR_PLAFOND-0.18, math.radians(135)),
    ( OX-0.8,  OY-0.8, ZP+HAUTEUR_PLAFOND-0.18, math.radians(-135)),
]
for l in range(NB_LIGNES):
    vy = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE + LARGEUR_VOIE/2
    cam_pts += [
        ( TOTAL_W/3, vy, ZP+HAUTEUR_PLAFOND-0.18, math.radians(90)),
        (-TOTAL_W/3, vy, ZP+HAUTEUR_PLAFOND-0.18, math.radians(-90)),
    ]
for cp in cam_pts:
    make_security_cam(*cp)

# ============================================================
#  SIGNALÉTIQUE + SÉCURITÉ
# ============================================================
for ex, ey in [(-OX+0.4, 0), (OX-0.4, 0), (0, OY-0.4)]:
    box((ex, ey, ZP+HAUTEUR_PLAFOND-0.13), (0.22, 0.035, 0.09), 'vert',     "Signalétique")
    box((ex, ey-0.04, ZP+HAUTEUR_PLAFOND-0.13), (0.20, 0.003, 0.07), 'neon_vert', "Signalétique")

for l in range(NB_LIGNES):
    vy = l*(LONGUEUR_PLACE+LARGEUR_VOIE) - OY + LONGUEUR_PLACE + LARGEUR_VOIE/2
    cyl((-OX+2, vy,     ZP+HAUTEUR_PLAFOND-0.22), 0.2,  0.035, 'rouge', "Signalétique", rot=(math.pi/2,0,0))
    cyl((-OX+2, vy-0.02,ZP+HAUTEUR_PLAFOND-0.22), 0.16, 0.003, 'blanc', "Signalétique", rot=(math.pi/2,0,0))

for ex, ey in [(-OX+0.25,-OY+4),(-OX+0.25,0),(-OX+0.25,OY-4),
               ( OX-0.25,-OY+4),( OX-0.25,0),( OX-0.25,OY-4)]:
    cyl((ex, ey, ZP+0.5),  0.065, 0.75, 'rouge',     "Sécurité")
    cyl((ex, ey, ZP+0.92), 0.035, 0.1,  'metal',     "Sécurité")
    box((ex-0.11, ey, ZP+0.5), (0.09, 0.04, 0.04),   'metal_dark', "Sécurité")

# ============================================================
#  ÉCLAIRAGE GLOBAL
# ============================================================
add_light('AREA', (0, 0, ZP+HAUTEUR_PLAFOND-0.05),
          energy=80, color=(0.88,0.92,1.0),
          rot=(math.pi,0,0), size=TOTAL_W+4, size_y=TOTAL_D+4)

# ============================================================
#  CAMÉRA DE RENDU
# ============================================================
bpy.ops.object.camera_add(
    location=(0, -OY-3, ZP+HAUTEUR_PLAFOND*0.6),
    rotation=(math.radians(75), 0, 0))
cam = bpy.context.object
cam.data.lens     = 22
cam.data.clip_end = 300
bpy.context.scene.camera = cam

# ============================================================
#  RENDU CYCLES
# ============================================================
scene = bpy.context.scene
scene.render.engine        = 'CYCLES'
scene.cycles.samples       = 128
scene.cycles.use_denoising = True
scene.render.resolution_x  = 1920
scene.render.resolution_y  = 1080

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
nt = world.node_tree
nt.nodes.clear()
bg  = nt.nodes.new('ShaderNodeBackground')
out = nt.nodes.new('ShaderNodeOutputWorld')
nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
bg.inputs['Color'].default_value    = (0.01, 0.01, 0.012, 1)
bg.inputs['Strength'].default_value = 0.0

COLS["Lumieres"].hide_viewport = True

# ============================================================
#  CENTRER LA VUE
# ============================================================
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for region in area.regions:
            if region.type == 'WINDOW':
                ctx = bpy.context.copy()
                ctx['area']   = area
                ctx['region'] = region
                try:
                    bpy.ops.view3d.view_all(ctx, center=True)
                except:
                    pass
                break

# ============================================================
#  SCRIPT MISE À JOUR TEMPS RÉEL (créé automatiquement dans Blender)
# ============================================================
UPDATE_SCRIPT = '''
# ── MISE À JOUR TEMPS RÉEL — PostgreSQL ─────────────────────
# Exécuter depuis l'éditeur Texte de Blender pour re-simuler
# les capteurs et mettre à jour les couleurs sans tout regénérer

import bpy, random, sys, site
from datetime import datetime

# Import psycopg2
try:
    import psycopg2
except ImportError:
    sys.path.append(site.getusersitepackages())
    import psycopg2

# ⚠️ Adapter si mot de passe différent
conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="parking", user="postgres", password="postgres123"
)
c   = conn.cursor()
now = datetime.now()

c.execute("SELECT id FROM places")
ids = [r[0] for r in c.fetchall()]

updated = 0
for pid in ids:
    etat = 'occupee' if random.random() < 0.55 else 'libre'
    c.execute("UPDATE places SET etat=%s, timestamp=%s WHERE id=%s", (etat, now, pid))
    c.execute("INSERT INTO historique (place_id, etat, timestamp) VALUES (%s,%s,%s)", (pid, etat, now))

    place_obj   = bpy.data.objects.get(f"Place_{pid}")
    capteur_obj = bpy.data.objects.get(f"Capteur_{pid}")
    if place_obj and capteur_obj:
        m_p = bpy.data.materials.get("Place_Libre"    if etat == "libre" else "Place_Occupee")
        m_c = bpy.data.materials.get("Capteur_Libre"  if etat == "libre" else "Capteur_Occupee")
        if m_p: place_obj.data.materials[0]   = m_p
        if m_c: capteur_obj.data.materials[0] = m_c
        updated += 1

conn.commit()
conn.close()

occupees = sum(1 for _ in ids if random.random() < 0.55)
print(f"✅ {updated} places mises à jour depuis PostgreSQL")
print(f"   Heure simulation : {now.strftime('%H:%M:%S')}")
'''

if "MiseAJour_PostgreSQL" not in bpy.data.texts:
    t = bpy.data.texts.new("MiseAJour_PostgreSQL")
    t.write(UPDATE_SCRIPT)

# ============================================================
#  RÉSUMÉ FINAL
# ============================================================
print("\n" + "="*58)
print("  ✅  PARKING V5 — PostgreSQL + CAPTEURS — SUCCÈS !")
print("="*58)
print(f"  📐 Dimensions    : {TOTAL_W:.0f}m × {TOTAL_D:.0f}m")
print(f"  🏠 Places actives: {NB_LIGNES*PLACES_PAR_LIGNE - len(DEGAGEMENT_L1)}")
print(f"  🟢 Libres        : {stats['libres']}")
print(f"  🔴 Occupées      : {stats['occupees']}")
print(f"  📈 Saturation    : {stats['taux']:.1f}%")
print(f"  🐘 PostgreSQL    : {PG_HOST}:{PG_PORT}/{PG_DATABASE}")
print("="*58)
print("\n  LÉGENDE :")
print("  🟢 Vert  = Libre standard")
print("  🔴 Rouge = Occupée")
print("  🔵 Bleu  = Handicap libre")
print("  🟣 Violet= Électrique libre")
print("\n  ▶ F12 = Rendu Cycles")
print("  ▶ Éditeur Texte → 'MiseAJour_PostgreSQL' → Run = nouvelle simulation")