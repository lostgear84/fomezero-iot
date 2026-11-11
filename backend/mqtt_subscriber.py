"""
FOMEZERO - consumidor MQTT: assina os topicos do lote, persiste em SQLite,
responde ACK no topico /comando e exibe o alerta termico.

Uso:
    python mqtt_subscriber.py --db data/fomezero.db
"""
import argparse, json, os, signal, sqlite3, sys
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

BROKER, PORTA = "broker.hivemq.com", 1883

def abre_db(caminho):
    con = sqlite3.connect(caminho)
    con.executescript(open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8").read())
    con.commit()
    return con

def ts_para_utc(msg):
    if msg.get("ts_valido") and msg.get("ts"):
        return msg["ts"].replace("Z", "+00:00")
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def grava_telemetria(con, msg):
    con.execute(
        "INSERT OR IGNORE INTO leitura (lote_id, device_id, seq, ts, temp_c, umid_pct,"
        " caixa_presente, distancia_cm, limite_c, evento, estado, origem, payload_raw)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (msg["lote_id"], msg["device_id"], msg.get("seq"), ts_para_utc(msg),
         msg.get("temp_c"), msg.get("umid_pct"), int(bool(msg.get("caixa_presente"))),
         msg.get("distancia_cm"), msg.get("limite_c"), msg.get("evento"),
         msg.get("estado"), msg.get("origem"), json.dumps(msg, ensure_ascii=False)))
    con.commit()

def grava_alerta(con, msg):
    con.execute(
        "INSERT INTO alerta (lote_id, device_id, seq, ts, evento, temp_c, limite_c,"
        " duracao_acima_s, severidade, estado) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (msg["lote_id"], msg["device_id"], msg.get("seq"), ts_para_utc(msg),
         msg.get("evento", "quebra_cadeia_frio"), msg.get("temp_c"), msg.get("limite_c"),
         msg.get("duracao_acima_s"), msg.get("severidade"), msg.get("estado", "ativo")))
    con.commit()

def notifica_telegram(msg):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    import urllib.parse, urllib.request
    texto = (f"ALERTA FOMEZERO - quebra de cadeia de frio\nLote {msg['lote_id']}\n"
             f"{msg.get('temp_c')} C (limite {msg.get('limite_c')} C)")
    dados = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=dados, timeout=5)

def on_connect(c, u, flags, rc, props=None):
    print(f"[MQTT] conectado rc={rc} em {BROKER}", flush=True)
    c.subscribe([("fomezero/gs2026/+/lote/+/telemetria", 1),
                 ("fomezero/gs2026/+/lote/+/alerta", 1),
                 ("fomezero/gs2026/+/lote/+/status", 1)])

def on_message(c, u, m):
    try:
        msg = json.loads(m.payload.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"[WARN] payload invalido em {m.topic}", flush=True)
        return

    schema = msg.get("schema", "")

    if schema == "fomezero.telemetria.v1":
        grava_telemetria(c.con, msg)
        topico_ack = m.topic.replace("/telemetria", "/comando")
        c.publish(topico_ack,
                  json.dumps({"schema": "fomezero.ack.v1",
                              "lote_id": msg.get("lote_id"),
                              "seq": msg.get("seq"),
                              "estado": "recebido"}, ensure_ascii=False),
                  qos=1)
        print(f"[ACK] enviado para {topico_ack} seq={msg.get('seq')}", flush=True)
        print(f"[TELEMETRIA] seq={msg.get('seq')} temp={float(msg.get('temp_c') or 0):.1f} C "
              f"umid={float(msg.get('umid_pct') or 0):.1f}% caixa={msg.get('caixa_presente')} "
              f"evento={msg.get('evento')} origem={msg.get('origem')}", flush=True)

    elif schema == "fomezero.alerta.v1":
        grava_alerta(c.con, msg)
        print(f"[ALERTA] {msg.get('evento')} lote={msg.get('lote_id')} "
              f"temp={float(msg.get('temp_c') or 0):.1f} C "
              f"limite={float(msg.get('limite_c') or 0):.1f} C "
              f"estado={msg.get('estado','ativo')}", flush=True)
        if msg.get("estado", "ativo") == "ativo":
            notifica_telegram(msg)

    elif schema == "fomezero.status.v1":
        print(f"[STATUS] {msg.get('device_id')} -> {msg.get('estado')}", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/fomezero.db")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    con = abre_db(args.db)
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fomezero-consumer-01")
    cli.con = con
    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(BROKER, PORTA, 30)
    signal.signal(signal.SIGINT, lambda *a: (cli.disconnect(), con.close(), sys.exit(0)))
    print(f"[INFO] assinando fomezero/gs2026/# | banco: {args.db}", flush=True)
    cli.loop_forever()

if __name__ == "__main__":
    main()
