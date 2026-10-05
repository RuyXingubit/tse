"""Intervalo adaptativo entre ciclos (PRD §6).

- 10 min enquanto houver progresso;
- 1 h depois de 24 h sem novidade;
- 6 h depois de 48 h sem novidade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PoliticaIntervalo:
    normal: timedelta = timedelta(minutes=10)
    lento: timedelta = timedelta(hours=1)
    muito_lento: timedelta = timedelta(hours=6)
    apos_lento: timedelta = timedelta(hours=24)
    apos_muito_lento: timedelta = timedelta(hours=48)
    apos_erro: timedelta = timedelta(minutes=2)

    def proximo(self, ultimo_progresso: datetime, agora: datetime) -> timedelta:
        parado = agora - ultimo_progresso
        if parado >= self.apos_muito_lento:
            return self.muito_lento
        if parado >= self.apos_lento:
            return self.lento
        return self.normal
