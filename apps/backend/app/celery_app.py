from celery import Celery
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Redis Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Initialize Celery
celery_app = Celery("transcripthub", broker=REDIS_URL, backend=REDIS_URL)

# Optional configuration, see the application user guide.
celery_app.conf.update(
    result_expires=3600,
)

# Import tasks to ensure they are registered
# Note: We will create app.tasks next
celery_app.autodiscover_tasks(['app'])
