"""Select an SDD mode from an explicit request, project policy and assessed risks."""

MODES = ("auto", "off", "lite", "full")
RISK_LEVELS = ("none", "low", "material", "unknown")
RISKS = {
    "behavior": "comportamento",
    "feature": "novidade funcional",
    "contract": "contratos",
    "data": "dados",
    "security": "segurança",
    "service_cost": "custo de serviços",
    "volume": "volume de código",
    "complexity": "complexidade",
    "architecture": "arquitetura",
    "reversibility": "reversibilidade",
    "test_scope": "alcance dos testes",
}


def parse_risks(arguments):
    risks = {}
    for argument in arguments:
        name, _, level = argument.partition("=")
        if name not in RISKS or level not in RISK_LEVELS or name in risks:
            raise ValueError(f"Invalid or repeated risk assessment {argument!r}; use FACTOR=LEVEL")
        risks[name] = level
    return risks


def choose_mode(configured, requested=None, risks=None, *, assessed_low=False):
    mode = requested if requested is not None else configured
    if mode not in MODES:
        raise ValueError(f"Invalid SDD mode {mode!r}")
    if mode != "auto":
        return mode, "Escolha explícita" if requested is not None else "Política do projeto"
    risks = risks or {}
    material = [label for name, label in RISKS.items() if risks.get(name) == "material"]
    if material:
        return "full", f"Impacto material em {', '.join(material)}"
    default = "low" if assessed_low else "unknown"
    unknown = [label for name, label in RISKS.items() if risks.get(name, default) == "unknown"]
    if unknown:
        reason = ", ".join(unknown) if len(unknown) <= 3 else f"{len(unknown)} dimensões"
        return "full", f"Avaliação incompleta em {reason}"
    return "lite", "Avaliação concluída com impacto baixo"
