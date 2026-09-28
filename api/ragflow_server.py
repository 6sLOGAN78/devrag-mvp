import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from common.log_utils import init_root_logger, getLogger
init_root_logger("ragflow_server")
logger = getLogger("Server")
from quart import Quart, jsonify
from quart_auth import QuartAuth
from api.db.db_models import db
from api.utils import redis_conn, storage_client
from api.apps.user_app import user_app
from api.apps.dataset_api import dataset_app
from api.apps.document_api import document_app

app = Quart(__name__)
app.secret_key = "devrag-super-secret-key-12345-long-enough-for-sha256"
app.config["QUART_AUTH_COOKIE_NAME"] = "ragflow_session"
app.config["QUART_AUTH_COOKIE_SECURE"] = False
QuartAuth(app)

app.register_blueprint(user_app)
app.register_blueprint(dataset_app)
app.register_blueprint(document_app)

def check_db():
    try:
        db.execute_sql("SELECT 1")
        return True, {"status": "ok", "elapsed": "0.0"}
    except Exception as e:
        return False, {"status": "nok", "error": str(e)}

@app.route('/health', methods=['GET'])
async def health():
    return jsonify({"status": "ok", "engine": "python"})

@app.route('/api/v1/system/healthz', methods=['GET'])
@app.route('/api/health', methods=['GET'])
async def api_health():
    is_ok, db_status = check_db()
    return jsonify({
        "status": "ok" if is_ok else "nok",
        "engine": "python",
        "db": db_status
    })

if __name__ == '__main__':
    # Run the Quart server on port 9380 to match NGINX expectations
    app.run(host='0.0.0.0', port=9380)
