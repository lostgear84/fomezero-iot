"""
Simulador de entrada MQTT - usado quando o ESP32 nao esta disponivel na hora da demo.
Publica as DUAS situacoes de entrada exigidas pelo enunciado (secao 3.e):
  A) temperatura normal (4,2 C) e caixa presente
  B) temperatura acima do limite (9,3 C) => evento quebra_cadeia_frio + alerta

Uso: python simulate_publish.py --cenario A|B|AB
"""
import argparse, json, time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

BASE = "fomezero/gs2026/rm564896/lote/LOTE-2026-0001"
LOTE, DEV = "LOTE-2026-0001", "esp32-simulado-01"

def agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def telemetria(seq, temp, umid, caixa, dist, evento, estado):
    return {"schema": "fomezero.telemetria.v1", "lote_id": LOTE, "device_id": DEV,
            "seq": seq, "ts": agora(), "ts_valido": True, "temp_c": temp, "umid_pct": umid,
            "caixa_presente": caixa, "distancia_cm": dist, "limite_c": 5.0,
            "evento": evento, "estado": estado, "origem": "simulador"}

def alerta(seq, temp):
    return {"schema": "fomezero.alerta.v1", "lote_id": LOTE, "device_id": DEV, "seq": seq,
            "ts": agora(), "evento": "quebra_cadeia_frio", "temp_c": temp, "limite_c": 5.0,
            "duracao_acima_s": 30, "severidade": "alta", "acao": "alerta_visual_app",
            "origem": "simulador"}

def publica(cli, topico, msg):
    cli.publish(f"{BASE}/{topico}", json.dumps(msg, ensure_ascii=False), qos=1)
    print(f"[TX] {topico}: {json.dumps(msg, ensure_ascii=False)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cenario", default="AB")
    a = ap.parse_args()
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fomezero-simulador")
    cli.connect("broker.hivemq.com", 1883, 30); cli.loop_start()
    seq = (int(time.time()) % 100000) * 10      # sessão por execução: nunca repete
    if "A" in a.cenario:
        print("--- CENARIO A: temperatura normal ---")
        for i in range(3):
            seq += 1
            publica(cli, "telemetria", telemetria(seq, round(4.2 - i * 0.1, 1), 71.5,
                                                  True, 12.4, "normal", "FRIO_OK"))
            time.sleep(1)
    if "B" in a.cenario:
        print("--- CENARIO B: acima do limite (5,0 C) ---")
        for t in (6.8, 8.1, 9.3):
            seq += 1
            publica(cli, "telemetria", telemetria(seq, t, 68.0, True, 12.1,
                                                  "quebra_cadeia_frio", "ALERTA"))
            time.sleep(1)
        seq += 1
        publica(cli, "alerta", alerta(seq, 9.3))
    time.sleep(1); cli.loop_stop(); cli.disconnect()

if __name__ == "__main__":
    main()
