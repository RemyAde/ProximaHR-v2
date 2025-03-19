from datetime import datetime
from pytz import UTC
from db import system_activity_collection  # Ensure you have this collection defined

async def log_admin_activity(admin_id: str = None, type: str = None, action: str = None, status: str = None):
    """
    Log an admin activity.

    Args:
        admin_id (str): The admin's identifier.
        action (str): Description of the admin activity.
        details (dict, optional): Additional details about the activity.
    """
    log_entry = {
        "admin_id": admin_id,
        "type": type,
        "action": action,
        "status": status,
        "timestamp": datetime.now(UTC)
    }
    await system_activity_collection.insert_one(log_entry)