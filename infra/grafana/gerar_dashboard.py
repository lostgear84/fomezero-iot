import json
from pathlib import Path

ds = {"type": "influxdb", "uid": "fomezero-influx"}

def consulta(campo, ultimo=False):
    q = (
        'from(bucket: "iot")\n'
        '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
        '  |> filter(fn: (r) => r._measurement == "telemetria")\n'
        '  |> filter(fn: (r) => r.lote_id == "LOTE-2026-0001")\n'
        '  |> filter(fn: (r) => r._field == "' + campo + '")\n'
    )
    if ultimo:
        q += '  |> last()\n'
    else:
        q += (
            '  |> aggregateWindow(every: v.windowPeriod, '
            'fn: mean, createEmpty: false)\n'
        )
    return q

def painel(id, titulo, tipo, campo, x, y, w, h, unidade="none"):
    stat = tipo == "stat"
    return {
        "id": id,
        "title": titulo,
        "type": tipo,
        "datasource": ds,
        "gridPos": {"x":x,"y":y,"w":w,"h":h},
        "targets": [{
            "refId":"A", "datasource":ds,
            "query":consulta(campo, stat)
        }],
        "fieldConfig": {
            "defaults": {
                "unit":unidade,
                "decimals":1,
                "mappings":[],
                "thresholds":{
                    "mode":"absolute",
                    "steps":[{"color":"green","value":None}]
                }
            },
            "overrides":[]
        },
        "options":{
            "reduceOptions":{"calcs":["lastNotNull"],"fields":"","values":False},
            "colorMode":"value",
            "graphMode":"none",
            "legend":{"displayMode":"list","placement":"bottom"}
        }
    }

panels = [
    {
        "id":1,"type":"text","title":"FOMEZERO - cadeia de frio",
        "gridPos":{"x":0,"y":0,"w":24,"h":3},
        "options":{
            "mode":"markdown",
            "content":
                "Lote: **LOTE-2026-0001** · ESP32 físico + DHT22 + HC-SR04\n\n"
                "Monitoramento de apoio à triagem. Não determina segurança para consumo. "
                "Os cartões mostram a última amostra dentro do período selecionado; "
                "confira sua idade no painel abaixo."
        }
    },
    painel(2,"Temperatura - ultima amostra","stat","temp_c",0,3,6,4,"celsius"),
    painel(3,"Umidade - ultima amostra","stat","umid_pct",6,3,6,4,"percent"),
    painel(4,"Presenca da caixa","stat","caixa_presente",12,3,6,4),
    painel(5,"Alerta termico confirmado","stat","alerta_ativo",18,3,6,4),
    painel(6,"Historico de temperatura","timeseries","temp_c",0,7,16,8,"celsius"),
    painel(7,"Historico de umidade","timeseries","umid_pct",16,7,8,8,"percent"),
    painel(8,"Distancia medida","timeseries","distancia_cm",0,15,12,7,"lengthcm"),
]

for p in panels:
    if p["id"] == 4:
        p["fieldConfig"]["defaults"]["decimals"] = 0
        p["fieldConfig"]["defaults"]["mappings"] = [{
            "type":"value","options":{
                "0":{"text":"AUSENTE"},
                "1":{"text":"PRESENTE"}
            }
        }]
    if p["id"] == 5:
        p["fieldConfig"]["defaults"]["decimals"] = 0
        p["fieldConfig"]["defaults"]["mappings"] = [{
            "type":"value","options":{
                "0":{"text":"SEM ALERTA","color":"green"},
                "1":{"text":"ALERTA ATIVO","color":"red"}
            }
        }]
    if p["id"] == 6:
        p["fieldConfig"]["defaults"]["thresholds"]["steps"].append(
            {"color":"red","value":5}
        )
        p["fieldConfig"]["defaults"]["custom"] = {
            "thresholdsStyle":{"mode":"line"}
        }

idade = painel(9,"Idade da ultima telemetria (s)","stat","seq",12,15,12,7,"s")
idade["targets"][0]["query"] = (
    'from(bucket: "iot")\n'
    '  |> range(start: -30d)\n'
    '  |> filter(fn: (r) => r._measurement == "telemetria" '
    'and r._field == "seq" and r.lote_id == "LOTE-2026-0001")\n'
    '  |> last()\n'
    '  |> map(fn: (r) => ({r with _value: '
    'float(v: int(v: now()) - int(v: r._time)) / 1000000000.0}))'
)
idade["fieldConfig"]["defaults"]["thresholds"]["steps"].append(
    {"color":"red","value":30}
)
panels.append(idade)

panels.append({
    "id":10,"type":"table","title":"Historico de eventos termicos",
    "datasource":ds,
    "gridPos":{"x":0,"y":22,"w":24,"h":8},
    "targets":[{
        "refId":"A","datasource":ds,
        "query":(
            'from(bucket: "iot")\n'
            '  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n'
            '  |> filter(fn: (r) => r._measurement == "alertas" '
            'and r.lote_id == "LOTE-2026-0001")\n'
            '  |> filter(fn: (r) => contains(value: r._field, '
            'set: ["temp_c","estado","evento"]))\n'
            '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], '
            'valueColumn: "_value")\n'
            '  |> group()\n'
            '  |> keep(columns: ["_time","device_id","temp_c","estado","evento"])\n'
            '  |> sort(columns: ["_time"], desc: true)\n'
            '  |> limit(n: 50)'
        )
    }],
    "options":{"showHeader":True},
    "fieldConfig":{"defaults":{},"overrides":[]}
})

dashboard = {
    "uid":"fomezero-iot",
    "title":"FOMEZERO - Monitoramento IoT",
    "schemaVersion":39,
    "version":1,
    "timezone":"browser",
    "refresh":"5s",
    "time":{"from":"now-30m","to":"now"},
    "panels":panels,
    "tags":["FOMEZERO","IoT"],
    "editable":True
}

destino = Path(__file__).parent / "dashboards" / "fomezero.json"
destino.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
print("Dashboard criado.")
