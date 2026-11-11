/*
 * FOMEZERO - Modulo IoT da cadeia de frio do lote de doacao
 * Global Solution 2026.2 - FIAP 2TIAPR-2026 - Physical Computing, Embedded AI, Robotics & Cognitive IoT
 * Equipe: Erick Miguel (RM 564896), Leonardo Melo (RM 567097), Luna Oliveira (RM 564215)
 *
 * Fluxo: entrada (DHT22 + HC-SR04) -> ESP32 -> MQTT -> banco + alerta no app
 * Simulado no Wokwi (ESP32 DevKit C v4). Ver docs/relatorio-iot.md secao 6.
 *
 * Bibliotecas (Library Manager): "DHT sensor library" (Adafruit) e "PubSubClient" (Nick O'Leary)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>

// ---------------- Configuracao ----------------
const char* WIFI_SSID   = "Wokwi-GUEST";
const char* WIFI_SENHA  = "";
const char* MQTT_HOST   = "broker.hivemq.com";   // broker publico gratuito (sem autenticacao)
const uint16_t MQTT_PORTA = 1883;

const char* LOTE_ID   = "LOTE-2026-0001";        // MESMO id usado por FEMD, AIPA e GABA
const char* DEVICE_ID = "esp32-caixa-01";

// Topicos base (prefixo com o RM evita colisao no broker publico)
const char* TOPICO_BASE      = "fomezero/gs2026/rm564896/lote/LOTE-2026-0001";
const char* TOPICO_TELEMETRIA = "fomezero/gs2026/rm564896/lote/LOTE-2026-0001/telemetria";
const char* TOPICO_ALERTA     = "fomezero/gs2026/rm564896/lote/LOTE-2026-0001/alerta";
const char* TOPICO_STATUS     = "fomezero/gs2026/rm564896/lote/LOTE-2026-0001/status";

// ---------------- Limite de conservacao ----------------
// ANVISA RDC 216/2004, item 4.8.16: alimento preparado refrigerado deve ser
// conservado abaixo de 5 C (congelado a -18 C ou menos). Cartilha ANVISA:
// zona de perigo 5 C a 60 C. Portanto: temp_c > 5.0 => quebra da cadeia de frio.
const float LIMITE_C     = 5.0;
const float HISTERESE_C  = 4.5;   // so normaliza abaixo disso (evita oscilacao no limite)

// ---------------- Temporizacao ----------------
const unsigned long INTERVALO_LEITURA_MS  = 2000;   // le sensores
const unsigned long INTERVALO_ENVIO_MS    = 10000;  // publica telemetria
const unsigned long CONFIRMA_ALERTA_MS    = 30000;  // 30 s acima do limite => alerta
const unsigned long CONFIRMA_NORMAL_MS    = 60000;  // 60 s abaixo da histerese => normalizacao

// ---------------- Pinos ----------------
#define PINO_DHT   15
#define TIPO_DHT   DHT22
#define PINO_TRIG  5
#define PINO_ECHO  18
#define PINO_LED   2
#define LIMIAR_CAIXA_CM 30.0          // < 30 cm => caixa presente no ponto de coleta

DHT dht(PINO_DHT, TIPO_DHT);
WiFiClient espClient;
PubSubClient mqtt(espClient);

// ---------------- Estado ----------------
float tempC = NAN, umidPct = NAN, distCm = NAN;
bool  caixaPresente = false;
bool  emAlerta = false;
unsigned long ultimaLeitura = 0, ultimoEnvio = 0;
unsigned long inicioAcima = 0, inicioAbaixo = 0;
unsigned long seq = 0;
bool tsValido = false;

// Buffer de retransmissao (mensagens geradas sem conexao MQTT)
#define BUF_MAX 8
String bufferTopicos[BUF_MAX];
String bufferPayloads[BUF_MAX];
uint8_t bufIni = 0, bufQtd = 0;

void enfileira(const char* topico, const String& payload) {
  if (bufQtd == BUF_MAX) { bufIni = (bufIni + 1) % BUF_MAX; bufQtd--; }  // descarta a mais antiga
  uint8_t idx = (bufIni + bufQtd) % BUF_MAX;
  bufferTopicos[idx] = String(topico);
  bufferPayloads[idx] = payload;
  bufQtd++;
}

void drenaBuffer() {
  while (bufQtd > 0 && mqtt.connected()) {
    if (!mqtt.publish(bufferTopicos[bufIni].c_str(), bufferPayloads[bufIni].c_str(), false)) return;
    bufIni = (bufIni + 1) % BUF_MAX;
    bufQtd--;
  }
}

void publica(const char* topico, const String& payload) {
  if (mqtt.connected() && mqtt.publish(topico, payload.c_str(), false)) {
    Serial.printf("[MQTT] publicado em %s (%u bytes, fila=%u)\n", topico, payload.length(), bufQtd);
    return;
  }
  enfileira(topico, payload);
  Serial.printf("[MQTT] offline: mensagem enfileirada (fila=%u)\n", bufQtd);
}

String agoraISO() {
  time_t agora = time(nullptr);
  if (agora < 1700000000) { tsValido = false; return String("1970-01-01T00:00:00Z"); }
  tsValido = true;
  struct tm t;
  gmtime_r(&agora, &t);
  char buf[24];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

void leSensores() {
  float t = dht.readTemperature();
  float u = dht.readHumidity();
  if (!isnan(t)) tempC = t;
  if (!isnan(u)) umidPct = u;

  digitalWrite(PINO_TRIG, LOW); delayMicroseconds(3);
  digitalWrite(PINO_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PINO_TRIG, LOW);
  long dur = pulseIn(PINO_ECHO, HIGH, 30000);
  if (dur > 0) {
    distCm = dur / 58.0;
    caixaPresente = (distCm < LIMIAR_CAIXA_CM);
  } else {
    distCm = NAN;
    caixaPresente = false;
  }
}

void conectaWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.printf("[WiFi] conectando em %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) delay(200);
  Serial.printf("[WiFi] status=%d ip=%s\n", (int)WiFi.status(), WiFi.localIP().toString().c_str());
}

void conectaMQTT() {
  if (mqtt.connected()) return;
  String clientId = String("fomezero-") + DEVICE_ID + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  // Last Will and Testament: se o ESP32 cair, o app recebe "offline" (retido)
  String lwt = String("{\"schema\":\"fomezero.status.v1\",\"lote_id\":\"") + LOTE_ID +
               "\",\"device_id\":\"" + DEVICE_ID + "\",\"estado\":\"offline\"}";
  if (mqtt.connect(clientId.c_str(), nullptr, nullptr, TOPICO_STATUS, 1, true, lwt.c_str())) {
    Serial.println("[MQTT] conectado ao broker");
    String on = String("{\"schema\":\"fomezero.status.v1\",\"lote_id\":\"") + LOTE_ID +
                "\",\"device_id\":\"" + DEVICE_ID + "\",\"estado\":\"online\"}";
    mqtt.publish(TOPICO_STATUS, on.c_str(), true);
    drenaBuffer();
  } else {
    Serial.printf("[MQTT] falha rc=%d\n", mqtt.state());
  }
}

String payloadTelemetria() {
  char buf[420];
  float t = isnan(tempC)   ? -127.0f : tempC;   // -127 = falha de leitura do DHT22
  float u = isnan(umidPct) ? 0.0f    : umidPct;
  float d = isnan(distCm)  ? 0.0f    : distCm;

  snprintf(buf, sizeof(buf),
    "{\"schema\":\"fomezero.telemetria.v1\",\"lote_id\":\"%s\",\"device_id\":\"%s\","
    "\"seq\":%lu,\"ts\":\"%s\",\"ts_valido\":%s,\"uptime_ms\":%lu,"
    "\"temp_c\":%.1f,\"umid_pct\":%.1f,\"caixa_presente\":%s,\"distancia_cm\":%.1f,"
    "\"limite_c\":%.1f,\"evento\":\"%s\",\"estado\":\"%s\",\"origem\":\"wokwi\"}",
    LOTE_ID, DEVICE_ID, seq, agoraISO().c_str(), tsValido ? "true" : "false",
    millis(), t, u, caixaPresente ? "true" : "false", d,
    LIMITE_C, emAlerta ? "quebra_cadeia_frio" : "normal",
    emAlerta ? "ALERTA" : "FRIO_OK");
  return String(buf);
}

String payloadAlerta(unsigned long duracaoS) {
  char buf[420];
  snprintf(buf, sizeof(buf),
    "{\"schema\":\"fomezero.alerta.v1\",\"lote_id\":\"%s\",\"device_id\":\"%s\","
    "\"seq\":%lu,\"ts\":\"%s\",\"evento\":\"quebra_cadeia_frio\","
    "\"temp_c\":%.1f,\"limite_c\":%.1f,\"duracao_acima_s\":%lu,\"severidade\":\"alta\","
    "\"acao\":\"alerta_visual_app\",\"origem\":\"wokwi\"}",
    LOTE_ID, DEVICE_ID, seq, agoraISO().c_str(), tempC, LIMITE_C, duracaoS);
  return String(buf);
}

void avaliaEstado() {
  if (isnan(tempC)) return;

  if (!emAlerta) {
    if (tempC > LIMITE_C) {
      if (inicioAcima == 0) inicioAcima = millis();
      if (millis() - inicioAcima >= CONFIRMA_ALERTA_MS) {
        emAlerta = true;
        inicioAbaixo = 0;
        digitalWrite(PINO_LED, HIGH);
        publica(TOPICO_ALERTA, payloadAlerta((millis() - inicioAcima) / 1000));
        Serial.printf("[ALERTA] quebra_cadeia_frio temp=%.1f C > limite %.1f C\n", tempC, LIMITE_C);
      }
    } else {
      inicioAcima = 0;
    }
  } else {
    if (tempC < HISTERESE_C) {
      if (inicioAbaixo == 0) inicioAbaixo = millis();
      if (millis() - inicioAbaixo >= CONFIRMA_NORMAL_MS) {
        emAlerta = false;
        inicioAcima = 0;
        inicioAbaixo = 0;
        digitalWrite(PINO_LED, LOW);
        String fim = String("{\"schema\":\"fomezero.alerta.v1\",\"lote_id\":\"") + LOTE_ID +
                     "\",\"seq\":" + String(seq) + ",\"ts\":\"" + agoraISO() +
                     "\",\"evento\":\"quebra_cadeia_frio\",\"estado\":\"normalizado\",\"temp_c\":" +
                     String(tempC, 1) + "}";
        publica(TOPICO_ALERTA, fim);
        Serial.println("[ALERTA] normalizado: temperatura voltou abaixo da histerese");
      }
    } else {
      inicioAbaixo = 0;
    }
  }
  digitalWrite(PINO_LED, emAlerta ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_TRIG, OUTPUT);
  pinMode(PINO_ECHO, INPUT);
  pinMode(PINO_LED, OUTPUT);
  digitalWrite(PINO_LED, LOW);
  dht.begin();
  delay(2000);
  Serial.println("\n=== FOMEZERO IoT - cadeia de frio / lote " + String(LOTE_ID) + " ===");

  conectaWiFi();
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setKeepAlive(20);
  mqtt.setBufferSize(512);
  conectaMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectaWiFi();
  if (!mqtt.connected()) conectaMQTT();
  mqtt.loop();

  unsigned long agora = millis();
  if (agora - ultimaLeitura >= INTERVALO_LEITURA_MS) {
    ultimaLeitura = agora;
    leSensores();
    avaliaEstado();
  }

  if (agora - ultimoEnvio >= INTERVALO_ENVIO_MS) {
    ultimoEnvio = agora;
    seq++;
    publica(TOPICO_TELEMETRIA, payloadTelemetria());
  }
}
