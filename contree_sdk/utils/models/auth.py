from dataclasses import dataclass, field


@dataclass
class WhoAmI:
    token_uuid: str
    token_expiration: int | None
    permissions: dict[str, bool] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=dict)
    operations_stat: dict = field(default_factory=dict)
