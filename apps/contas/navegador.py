"""Nome legível do navegador a partir do User-Agent, para o histórico de acessos."""

# A ordem importa: o Edge também se anuncia como Chrome e Safari, e o Chrome como Safari.
NAVEGADORES = (
    (("Edg/", "EdgA/", "EdgiOS/"), "Edge"),
    (("Chrome/", "CriOS/"), "Chrome"),
    (("Firefox/", "FxiOS/"), "Firefox"),
    (("Safari/",), "Safari"),
)

# O Android também se anuncia como Linux, e o iPhone e o iPad "como o Mac OS X".
SISTEMAS = (
    ("Windows", "Windows"),
    ("Android", "Android"),
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Macintosh", "Mac"),
    ("Linux", "Linux"),
)


def navegador_legivel(user_agent: str) -> str:
    """Ex.: "Chrome no Windows". Sem reconhecer o navegador, "Navegador desconhecido"."""
    navegador = next(
        (nome for marcas, nome in NAVEGADORES if any(m in user_agent for m in marcas)),
        "Navegador desconhecido",
    )
    sistema = next((nome for marca, nome in SISTEMAS if marca in user_agent), None)
    return f"{navegador} no {sistema}" if sistema else navegador
