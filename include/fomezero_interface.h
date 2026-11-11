#pragma once
#include <Arduino.h>

namespace InterfaceFomezero {
  void iniciar();

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
  );
}
