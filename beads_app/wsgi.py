from app import app, get_db_connection
from cloud_bridge import register
register(app, get_db_connection)
app.config.update(DEBUG=False, MAX_CONTENT_LENGTH=81*1024*1024)
