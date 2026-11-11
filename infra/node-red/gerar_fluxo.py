import json
from pathlib import Path

converter = r'''
try {
    let p = typeof msg.payload === "string"
        ? JSON.parse(msg.payload)
        : msg.payload;

    if (!p || typeof p !== "object") {
        throw new Error("Payload deve ser objeto");
    }

    if (!p.lote_id || !p.device_id) {
        throw new Error("lote_id ou device_id ausente");
    }

    const telemetria = p.schema === "fomezero.telemetria.v1";
    const alerta = p.schema === "fomezero.alerta.v1";

    if (!telemetria && !alerta) return null;

    function tag(v) {
        return String(v).replace(/\\/g, "\\\\")
                        .replace(/ /g, "\\ ")
                        .replace(/,/g, "\\,")
                        .replace(/=/g, "\\=");
    }

    function str(v) {
        return '"' + String(v).replace(/\\/g, "\\\\")
                              .replace(/"/g, '\\"')
                              .replace(/[\r\n]/g, " ") + '"';
    }

    const campos = [];

    function numero(nome, valor) {
        if (typeof valor === "number" && Number.isFinite(valor)) {
            campos.push(nome + "=" + valor);
        }
    }

    // Compatibilidade com o firmware atual, que usa -127 para falha.
    if (typeof p.temp_c === "number" && p.temp_c !== -127) {
        numero("temp_c", p.temp_c);
    }

    numero("umid_pct", p.umid_pct);
    numero("limite_c", p.limite_c);
    numero("seq", p.seq);
    numero("duracao_acima_s", p.duracao_acima_s);

    if (typeof p.distancia_cm === "number" && p.distancia_cm > 0) {
        numero("distancia_cm", p.distancia_cm);
    }

    if (telemetria) {
        campos.push("caixa_presente=" + (p.caixa_presente ? 1 : 0));
        campos.push("alerta_ativo=" + (p.estado === "ALERTA" ? 1 : 0));
    }

    campos.push("evento=" + str(p.evento || ""));
    campos.push("estado=" + str(p.estado || (alerta ? "ativo" : "")));
    campos.push("ts_dispositivo=" + str(p.ts || ""));

    const measurement = telemetria ? "telemetria" : "alertas";
    const tags = ",lote_id=" + tag(p.lote_id)
        + ",device_id=" + tag(p.device_id)
        + ",origem=" + tag(p.origem || "nao_informada");

    // Horario de ingestao no servidor. O timestamp do ESP32 fica em campo separado.
    msg.payload = measurement + tags + " " + campos.join(",");

    msg.method = "POST";
    msg.url = env.get("INFLUX_URL")
        + "/api/v2/write?org=" + encodeURIComponent(env.get("INFLUX_ORG"))
        + "&bucket=" + encodeURIComponent(env.get("INFLUX_BUCKET"))
        + "&precision=ms";

    msg.headers = {
        "Authorization": "Token " + env.get("INFLUX_TOKEN"),
        "Content-Type": "text/plain; charset=utf-8"
    };

    msg.fz = {
        telemetria: telemetria,
        lote_id: p.lote_id,
        device_id: p.device_id,
        seq: p.seq,
        topico_ack: msg.topic.replace(/\/telemetria$/, "/comando")
    };

    return msg;
} catch (erro) {
    node.error("Mensagem rejeitada: " + erro.message, msg);
    return null;
}
'''

confirmar = r'''
if (msg.statusCode !== 204) {
    node.error("InfluxDB recusou escrita: HTTP " + msg.statusCode
        + " " + String(msg.payload), msg);
    return null;
}

if (!msg.fz || !msg.fz.telemetria) return null;

msg.topic = msg.fz.topico_ack;
msg.payload = JSON.stringify({
    schema: "fomezero.ack.v1",
    lote_id: msg.fz.lote_id,
    device_id: msg.fz.device_id,
    seq: msg.fz.seq,
    estado: "persistido_influxdb"
});
delete msg.headers;
delete msg.url;
return msg;
'''

flows = [
    {"id":"fz-tab","type":"tab","label":"FOMEZERO - IoT","disabled":False,"info":""},
    {
        "id":"fz-broker","type":"mqtt-broker","name":"Mosquitto local",
        "broker":"mosquitto","port":"1883","clientid":"fomezero-nodered",
        "autoConnect":True,"usetls":False,"protocolVersion":"4",
        "keepalive":"60","cleansession":True
    },
    {
        "id":"fz-in","type":"mqtt in","z":"fz-tab","name":"Entrada do ESP32",
        "topic":"fomezero/gs2026/rm564896/lote/+/#","qos":"1",
        "datatype":"utf8","broker":"fz-broker",
        "x":150,"y":120,"wires":[["fz-converter"]]
    },
    {
        "id":"fz-converter","type":"function","z":"fz-tab",
        "name":"Validar e preparar InfluxDB","func":converter,
        "outputs":1,"x":410,"y":120,"wires":[["fz-http"]]
    },
    {
        "id":"fz-http","type":"http request","z":"fz-tab",
        "name":"Gravar no InfluxDB","method":"use","ret":"txt",
        "paytoqs":"ignore","url":"","persist":False,
        "x":680,"y":120,"wires":[["fz-confirmar"]]
    },
    {
        "id":"fz-confirmar","type":"function","z":"fz-tab",
        "name":"ACK somente apos HTTP 204","func":confirmar,
        "outputs":1,"x":680,"y":220,"wires":[["fz-out","fz-debug"]]
    },
    {
        "id":"fz-out","type":"mqtt out","z":"fz-tab",
        "name":"ACK ao ESP32","topic":"","qos":"1",
        "retain":"false","broker":"fz-broker",
        "x":950,"y":180,"wires":[]
    },
    {
        "id":"fz-debug","type":"debug","z":"fz-tab",
        "name":"ACK de persistencia","active":True,
        "tosidebar":True,"console":False,
        "complete":"payload","targetType":"msg",
        "x":960,"y":260,"wires":[]
    },
    {
        "id":"fz-catch","type":"catch","z":"fz-tab",
        "name":"Capturar erros","scope":None,"uncaught":False,
        "x":180,"y":340,"wires":[["fz-erros"]]
    },
    {
        "id":"fz-erros","type":"debug","z":"fz-tab",
        "name":"ERROS","active":True,"tosidebar":True,"console":True,
        "complete":"error.message","targetType":"msg",
        "x":430,"y":340,"wires":[]
    }
]

Path(__file__).with_name("flows.json").write_text(
    json.dumps(flows, indent=2), encoding="utf-8"
)
print("Fluxo Node-RED criado.")
