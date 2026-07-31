from app.crm_connectors.base import CRMConnector
from app.crm_connectors.followupboss import FollowUpBossConnector
from app.crm_connectors.hubspot import HubSpotConnector

_REGISTRY = {
    "followupboss": FollowUpBossConnector,
    "hubspot": HubSpotConnector,
}


def get_connector(provider: str, credentials: dict) -> CRMConnector:
    connector_cls = _REGISTRY.get(provider)
    if not connector_cls:
        raise ValueError(f"No live connector for provider '{provider}' (csv is handled separately, see csv_connector.py)")
    return connector_cls(credentials)
