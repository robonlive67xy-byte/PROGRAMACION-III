import json
from datetime import timedelta
from pathlib import Path

try:
    from minizinc import Model, Solver, Instance
except ImportError as e:
    print("Error: el paquete 'minizinc' no está instalado. Ejecuta 'pip install minizinc'.")
    raise SystemExit(1) from e

BASE_DIR = Path(__file__).resolve().parent
MODEL_FILE = BASE_DIR / "Models" / "Modelo_Solution.mzn"
DATA_JSON = BASE_DIR / "Data" / "materias.json"
DATA_DZN = BASE_DIR / "Data" / "salida.dzn"
SELECTED_AGENTS = BASE_DIR / "Data" / "selected_agents.json"
BASE_AGENT_FILE    = BASE_DIR / "Data" / "agent_base.json"
BASE_AGENT_LE_FILE = BASE_DIR / "Data" / "agent_base_le.json"
BASE_AGENT_MIN_FILE = BASE_DIR / "Data" / "agent_minimizar.json"
NO_VACIOS_FILE = BASE_DIR / "Data" / "agente_no_vacios.json"
LOW_AGENT_FILE = BASE_DIR / "Data" / "agent_low.json"
BASE_AGENT_BALANCE_FILE = BASE_DIR / "Data" / "agent_balance_master.json"

if not MODEL_FILE.exists():
    raise FileNotFoundError(f"No se encontró el modelo: {MODEL_FILE}")
if not DATA_JSON.exists():
    raise FileNotFoundError(f"No se encontró el archivo JSON: {DATA_JSON}")
if not DATA_DZN.exists():
    raise FileNotFoundError(f"No se encontró el archivo DZN generado por el engine: {DATA_DZN}")

with open(DATA_JSON, encoding="utf-8") as f:
    materias_data = json.load(f)

materias = list(materias_data.keys())

selected_agents = []
if SELECTED_AGENTS.exists():
    with open(SELECTED_AGENTS, encoding="utf-8") as f:
        selected_agents = json.load(f)

usar_agente_base = "base" in selected_agents
usar_agente_base_le = "base_menor_igual" in selected_agents
usar_agente_minimizar = "minimizar" in selected_agents
usar_agente_no_vacios = "agente_no_vacios" in selected_agents
usar_low_penalitation = "low_penalitation" in selected_agents
usar_stability = "Beta" in selected_agents

# ── target_creditos ─────────────────────────────────────────────────────────
target_creditos = 12
if usar_agente_minimizar and BASE_AGENT_MIN_FILE.exists():
    with open(BASE_AGENT_MIN_FILE, encoding="utf-8") as f:
        data = json.load(f)
        target_creditos = data.get("target_creditos", target_creditos)
elif usar_agente_base_le and BASE_AGENT_LE_FILE.exists():
    with open(BASE_AGENT_LE_FILE, encoding="utf-8") as f:
        data = json.load(f)
        target_creditos = data.get("target_creditos", target_creditos)
elif usar_agente_base and BASE_AGENT_FILE.exists():
    with open(BASE_AGENT_FILE, encoding="utf-8") as f:
        data = json.load(f)
        target_creditos = data.get("target_creditos", target_creditos)
elif usar_stability and BASE_AGENT_BALANCE_FILE.exists():
    with open(BASE_AGENT_BALANCE_FILE, encoding="utf-8") as f:
        data = json.load(f)
        target_creditos = data.get("target_creditos", target_creditos)
elif usar_low_penalitation and LOW_AGENT_FILE.exists():
    with open(LOW_AGENT_FILE, encoding="utf-8") as f:
        data = json.load(f)
        target_creditos = data.get("target_creditos", target_creditos)

print("=== Configuración de agentes ===")
print(f"Agentes seleccionados: {selected_agents}")
print(f"Usar agente base:             {usar_agente_base}")
print(f"Usar agente base_menor_igual: {usar_agente_base_le}")
print(f"Usar agente minimizar:        {usar_agente_minimizar}")
print(f"Usar agente no_vacios:        {usar_agente_no_vacios}")
print(f"Usar agente low:              {usar_low_penalitation}")
print(f"Usar agente estabilizador: {usar_stability}")
if usar_agente_base or usar_agente_base_le or usar_agente_minimizar or usar_stability or usar_low_penalitation:
    print(f"Target de créditos por semestre: {target_creditos}")
print()

# ── Acumulación de pesos SOLO para los agentes seleccionados ────────────────
#
# Mapa: nombre en selected_agents.json → archivo que lo define
AGENT_FILES = {
    "minimizar":        BASE_AGENT_MIN_FILE,
    "agente_no_vacios": NO_VACIOS_FILE,
    "low_penalitation": LOW_AGENT_FILE,
    "base":             BASE_AGENT_FILE,
    "base_menor_igual": BASE_AGENT_LE_FILE,
    "Beta":   BASE_AGENT_BALANCE_FILE 
}

# Normaliza la clave "empty_penalty" (usada en agente_no_vacios.json)
# al nombre que espera MiniZinc: "w_no_vacios"
KEY_ALIASES = {
    "w_balance":     "w_balance",
    "w_low":         "w_low",
    "w_no_vacios":   "w_no_vacios",
    "w_stability": "w_stability", 
       
}

w_balance  = 0
w_low      = 0
w_no_vacios = 0
w_stability = 0

for agent_name in selected_agents:
    file = AGENT_FILES.get(agent_name)
    if file is None:
        print(f"  [WARN] Agente desconocido '{agent_name}', se omite.")
        continue
    if not file.exists():
        print(f"  [WARN] Archivo para agente '{agent_name}' no encontrado: {file}")
        continue

    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    weights = data.get("weights", {})
    for raw_key, val in weights.items():
        normalized = KEY_ALIASES.get(raw_key)
        if normalized is None:
            print(f"  [WARN] Clave desconocida '{raw_key}' en {file.name}, se ignora.")
            continue
        if normalized == "w_balance":
            w_balance += val
        elif normalized == "w_low":
            w_low += val
        elif normalized == "w_no_vacios":
            w_no_vacios += val
        elif normalized == "w_stability":
            w_stability += val    

print("=== Pesos acumulados ===")
print(f"w_balance  = {w_balance}")
print(f"w_low      = {w_low}")
print(f"w_no_vacios = {w_no_vacios}")
print(f"w_stability = {w_stability}")
print()

# ── MiniZinc ─────────────────────────────────────────────────────────────────
modelo = Model(str(MODEL_FILE))
modelo.add_file(str(DATA_DZN))

gecode   = Solver.lookup("gecode")
instancia = Instance(gecode, modelo)

instancia["w_balance"]    = w_balance
instancia["w_low"]        = w_low
instancia["w_no_vacios"]  = w_no_vacios
instancia["target_creditos"] = target_creditos
instancia["min_load"]     = 10
instancia["w_stability"] = w_stability

resultado = instancia.solve(time_limit=timedelta(seconds=30))

if not resultado.solution:
    print("No se encontró una solución factible.")
    print(resultado)
    raise SystemExit(1)

print(f"\n=== Energías ===")
print(f"energia_no_vacios = {resultado['energia_no_vacios']}")
print(f"energia_balance   = {resultado['energia_balance']}")
print(f"energia_low       = {resultado['energia_low']}")
print(f"energia_stability = {resultado['energia_stability']}")

print("=== Resultado MiniZinc ===")
print(resultado)
print()
print("=== Detalle de semestres ===")
semestres = resultado["semestre"]
if len(semestres) != len(materias):
    raise ValueError(
        f"La cantidad de semestres devuelta ({len(semestres)}) "
        f"no coincide con las materias ({len(materias)})."
    )
for materia, semestre_asignado in zip(materias, semestres):
    print(f"{materia}: semestre {semestre_asignado}")

print()
print("=== Carga por semestre ===")
texto = str(resultado)
for line in texto.split("\n"):
    if "carga =" in line:
        inicio = line.find("[")
        fin    = line.find("]")
        lista  = line[inicio + 1:fin].split(",")
        for i, val in enumerate(lista, start=1):
            print(f"Semestre {i}: {val.strip()} créditos")
