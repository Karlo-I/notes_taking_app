from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize the limiter without an app (we will bind it in app_factory)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://" # Silences the warning for local dev
)