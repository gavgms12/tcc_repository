"""Parâmetros de negócio compartilhados entre as camadas."""

from __future__ import annotations

import os
from datetime import date

# Janela de relevância das produções/projetos/trabalhos de IC. Definida num só
# lugar (antes estava duplicada na Bronze e na Silver). Pode ser fixada por
# variável de ambiente para tornar a execução determinística.
ANO_MINIMO = int(os.getenv("ANO_MINIMO", date.today().year - 10))
