#include "fomezero_interface.h"
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <math.h>

namespace {
  Adafruit_SSD1306 display(128, 64, &Wire, -1);
  bool displayPronto = false;
  unsigned long ultimaAtualizacao = 0;

  void linha(uint8_t y, const String& texto) {
    display.setCursor(0, y);
    display.print(texto);
  }

  String numero(float valor) {
    return isnan(valor) ? String("--") : String(valor, 1);
  }
}

namespace InterfaceFomezero {

void iniciar() {
  Wire.begin(21, 22);

  displayPronto = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  if (!displayPronto) {
    Serial.println("[OLED] falha ao inicializar");
    return;
  }

  display.clearDisplay();
  display.setFont(nullptr);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setTextWrap(false);
  linha(0, "FOMEZERO IoT");
  display.display();

  Serial.println("[OLED] display inicializado");
}

void atualizar(
  float tempC,
  float umidPct,
  float distCm,
  bool caixaPresente,
  bool emAlerta,
  bool wifiConectado,
  bool mqttConectado,
  unsigned long inicioAcima,
  unsigned long inicioAbaixo,
  unsigned long confirmaAlertaMs,
  unsigned long confirmaNormalMs
) {
  if (!displayPronto) return;

  const unsigned long agora = millis();
  if (agora - ultimaAtualizacao < 250) return;
  ultimaAtualizacao = agora;

  display.clearDisplay();
  display.setFont(nullptr);
  display.setTextSize(1);
  display.setTextWrap(false);
  display.setTextColor(SSD1306_WHITE);

  linha(0,  "FOMEZERO IoT");
  linha(8,  String("Temp: ") + numero(tempC) + " C");
  linha(16, String("Umid: ") + numero(umidPct) + " %");
  linha(24, String("Dist: ") + numero(distCm) + " cm");
  linha(32, String("Caixa: ") +
      (caixaPresente ? "PRESENTE" : "AUSENTE"));

  linha(40, String("WiFi:") +
      (wifiConectado ? "OK" : "--") +
      " MQTT:" + (mqttConectado ? "OK" : "--"));

  // Linha exclusiva para estado.
  if (isnan(tempC)) {
    linha(48, "FALHA: TEMPERATURA");
  } else if (emAlerta) {
    linha(48, "ALERTA: CADEIA FRIO");
  } else if (inicioAcima != 0) {
    linha(48, "ACIMA DO LIMITE");
  } else {
    linha(48, "ESTADO: FRIO OK");
  }

  // Ultima linha exclusiva para limite ou temporizador.
  if (emAlerta && inicioAbaixo != 0) {
    const unsigned long decorrido = agora - inicioAbaixo;
    const unsigned long restante =
        decorrido >= confirmaNormalMs
        ? 0
        : (confirmaNormalMs - decorrido + 999) / 1000;

    linha(56, String("Normaliza em: ") + restante + "s");
  } else if (!emAlerta && inicioAcima != 0) {
    const unsigned long decorrido = agora - inicioAcima;
    const unsigned long restante =
        decorrido >= confirmaAlertaMs
        ? 0
        : (confirmaAlertaMs - decorrido + 999) / 1000;

    linha(56, String("Alerta em: ") + restante + "s");
  } else {
    linha(56, "Limite: 5.0 C");
  }

  display.display();
}

}
